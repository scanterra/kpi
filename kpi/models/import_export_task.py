# FIXME: clean up these imports!
import base64
from io import BytesIO
import datetime
import dateutil.parser
import re
import logging
import posixpath
import tempfile
from os.path import splitext
from collections import defaultdict
from django.db import models, transaction
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.urlresolvers import get_script_prefix, resolve
from django.utils.six.moves.urllib import parse as urlparse
from jsonfield import JSONField
import requests
from pyxform import xls2json_backends
from private_storage.fields import PrivateFileField
from kobo.apps.reports.report_data import build_formpack
from formpack import FormPack
import formpack.constants
from ..fields import KpiUidField
from ..models import Collection, Asset
from ..model_utils import create_assets, _load_library_content
from ..zip_importer import HttpContentParse
from rest_framework import exceptions


def _resolve_url_to_asset_or_collection(item_path):
    if item_path.startswith(('http', 'https')):
        item_path = urlparse.urlparse(item_path).path
        if settings.KPI_PREFIX and (settings.KPI_PREFIX != '/') and \
                item_path.startswith(settings.KPI_PREFIX):
            item_path = item_path.replace(settings.KPI_PREFIX, '', 1)
    match = resolve(item_path)
    uid = match.kwargs.get('uid')
    if match.url_name == 'asset-detail':
        return ('asset', Asset.objects.get(uid=uid))
    elif match.url_name == 'collection-detail':
        return ('collection', Collection.objects.get(uid=uid))


class ImportExportTask(models.Model):
    # DOCUMENTATION!!! #NOCOMMIT

    class Meta:
        abstract = True

    CREATED = 'created'
    PROCESSING = 'processing'
    COMPLETE = 'complete'
    ERROR = 'error'

    STATUS_CHOICES = (
        (CREATED, CREATED),
        (PROCESSING, PROCESSING),
        (ERROR, ERROR),
        (COMPLETE, COMPLETE),
    )

    user = models.ForeignKey('auth.User')
    data = JSONField()
    messages = JSONField(default={})
    status = models.CharField(choices=STATUS_CHOICES, max_length=32,
                              default=CREATED)
    date_created = models.DateTimeField(auto_now_add=True)
    # date_expired = models.DateTimeField(null=True)

    def run(self):
        # DOCUMENTATION!! #NOCOMMIT
        '''
        this could take a while.
        '''

        with transaction.atomic():
            refetched_self = self._meta.model.objects.get(pk=self.pk)
            self.status = refetched_self.status
            del refetched_self
            if self.status == self.COMPLETE:
                return
            elif self.status != self.CREATED:
                # possibly a concurrent task?
                raise Exception(
                    'only recently created % can be executed'.format(
                        self._meta.model_name)
                )
            self.status = self.PROCESSING
            self.save(update_fields=['status'])

        msgs = defaultdict(list)
        try:
            # This method must be implemented by a subclass
            self._run_task(msgs)
            self.status = self.COMPLETE
        except Exception, err:
            msgs['error_type'] = type(err).__name__
            msgs['error'] = err.message
            self.status = self.ERROR
            logging.error(
                'Failed to run %: %' % (self._meta.model_name, repr(err)),
                exc_info=True
            )

        self.messages.update(msgs)
        try:
            self.save(update_fields=['status', 'messages'])
        except TypeError, e:
            self.status = ImportTask.ERROR
            logging.error('Failed to save %: %' % (self._meta.model_name,
                                                   repr(e)),
                          exc_info=True)
            self.save(update_fields=['status'])


class ImportTask(ImportExportTask):
    uid = KpiUidField(uid_prefix='i')
    '''
    someting that would be done after the file has uploaded
    ...although we probably would need to store the file in a blob
    '''

    def _run_task(self, messages):
        self.status = self.PROCESSING
        self.save(update_fields=['status'])
        dest_item = dest_kls = has_necessary_perm = False

        if 'destination' in self.data and self.data['destination']:
            _d = self.data.get('destination')
            (dest_kls, dest_item) = _resolve_url_to_asset_or_collection(_d)
            necessary_perm = 'change_%s' % dest_kls
            if not dest_item.has_perm(self.user, necessary_perm):
                raise exceptions.PermissionDenied('user cannot update %s' % kls)
            else:
                has_necessary_perm = True

        if 'url' in self.data:
            self._load_assets_from_url(
                messages=messages,
                url=self.data.get('url'),
                destination=dest_item,
                destination_kls=dest_kls,
                has_necessary_perm=has_necessary_perm,
            )
        elif 'base64Encoded' in self.data:
            self._parse_b64_upload(
                base64_encoded_upload=self.data['base64Encoded'],
                filename=self.data.get('filename', None),
                messages=messages,
                library=self.data.get('library', False),
                destination=dest_item,
                destination_kls=dest_kls,
                has_necessary_perm=has_necessary_perm,
            )
        else:
            raise Exception(
                'ImportTask data must contain `base64Encoded` or `url`'
            )

    def _load_assets_from_url(self, url, messages, **kwargs):
        destination = kwargs.get('destination', False)
        destination_kls = kwargs.get('destination_kls', False)
        has_necessary_perm = kwargs.get('has_necessary_perm', False)
        req = requests.get(url, allow_redirects=True)
        fif = HttpContentParse(request=req).parse()
        fif.remove_invalid_assets()
        fif.remove_empty_collections()

        destination_collection = destination \
                if (destination_kls == 'collection') else False

        if destination_collection and not has_necessary_perm:
            # redundant check
            raise exceptions.PermissionDenied('user cannot load assets into this collection')

        collections_to_assign = []
        for item in fif._parsed:
            extra_args = {
                'owner': self.user,
                'name': item._name_base,
            }

            if item.get_type() == 'collection':
                item._orm = create_assets(item.get_type(), extra_args)
            elif item.get_type() == 'asset':
                kontent = xls2json_backends.xls_to_dict(item.readable)
                extra_args['content'] = _strip_header_keys(kontent)
                item._orm = create_assets(item.get_type(), extra_args)
            if item.parent:
                collections_to_assign.append([
                    item._orm,
                    item.parent._orm,
                ])
            elif destination_collection:
                collections_to_assign.append([
                    item._orm,
                    destination_collection,
                ])

        for (orm_obj, parent_item) in collections_to_assign:
            orm_obj.parent = parent_item
            orm_obj.save()

    def _parse_b64_upload(self, base64_encoded_upload, messages, **kwargs):
        filename = splitext(kwargs.get('filename', ''))[0]
        library = kwargs.get('library')
        survey_dict = _b64_xls_to_dict(base64_encoded_upload)
        survey_dict_keys = survey_dict.keys()

        destination = kwargs.get('destination', False)
        destination_kls = kwargs.get('destination_kls', False)
        has_necessary_perm = kwargs.get('has_necessary_perm', False)

        if destination and not has_necessary_perm:
            # redundant check
            raise exceptions.PermissionDenied('user cannot update item')

        if destination_kls == 'collection':
            raise NotImplementedError('cannot import into a collection at this'
                                      ' time')

        if 'library' in survey_dict_keys:
            if not library:
                raise ValueError('a library cannot be imported into the'
                                 ' form list')
            if 'survey' in survey_dict_keys:
                raise ValueError('An import cannot have both "survey" and'
                                 ' "library" sheets.')
            if destination:
                raise SyntaxError('libraries cannot be imported into assets')
            collection = _load_library_content({
                    'content': survey_dict,
                    'owner': self.user,
                    'name': filename
                })
            messages['created'].append({
                    'uid': collection.uid,
                    'kind': 'collection',
                    'owner__username': self.user.username,
                })
        elif 'survey' in survey_dict_keys:
            if not destination:
                if library and len(survey_dict.get('survey')) > 1:
                    asset_type = 'block'
                elif library:
                    asset_type = 'question'
                else:
                    asset_type = 'survey'
                asset = Asset.objects.create(
                    owner=self.user,
                    content=survey_dict,
                    asset_type=asset_type,
                    summary={'filename': filename},
                )
                msg_key = 'created'
            else:
                asset = destination
                asset.content = survey_dict
                asset.save()
                msg_key = 'updated'

            messages[msg_key].append({
                    'uid': asset.uid,
                    'summary': asset.summary,
                    'kind': 'asset',
                    'owner__username': self.user.username,
                })
        else:
            raise SyntaxError('xls upload must have one of these sheets: {}'
                              .format('survey, library'))


def export_upload_to(self, filename):
    '''
    Please note that due to Python 2 limitations, you cannot serialize unbound
    method functions (e.g. a method declared and used in the same class body).
    Please move the function into the main module body to use migrations.  For
    more information, see
    https://docs.djangoproject.com/en/1.8/topics/migrations/#serializing-values
    '''
    return posixpath.join(self.user.username, 'exports', filename)


class ExportTask(ImportExportTask):
    # DOCUMENTATION!!! #NOCOMMIT

    uid = KpiUidField(uid_prefix='e')
    last_submission_time = models.DateTimeField(null=True)
    result = PrivateFileField(upload_to=export_upload_to, max_length=380)

    COPY_FIELDS = ('_id', '_uuid', '_submission_time')
    TIMESTAMP_KEY = '_submission_time'

    @staticmethod
    def build_export_filename(export, extension):
        # DOCUMENTATION!!! #NOCOMMIT
        form_type = 'labels'
        if not export.lang:
            form_type = "values"
        elif export.lang != "_default":
            form_type = export.lang

        return "{title} - {form_type} - {date:%Y-%m-%d-%H-%M}.{ext}".format(
            form_type=form_type,
            date=datetime.datetime.utcnow(),
            title=export.title,
            ext=extension
        )

    def build_export_options(self, pack):
        # DOCUMENTATION!!! #NOCOMMIT
        hierarchy_in_labels = self.data.get(
            'hierarchy_in_labels', ''
        ).lower() == 'true'
        group_sep = self.data.get('group_sep', '/')
        translations = pack.available_translations
        lang = self.data.get('lang', None) or next(iter(translations), None)
        if lang == '_default':
            lang = formpack.constants.UNTRANSLATED

        return {
            'versions': pack.versions, # inefficient?
            'group_sep': group_sep,
            'lang': lang,
            'hierarchy_in_labels': hierarchy_in_labels,
            'copy_fields': self.COPY_FIELDS,
            'force_index': True,
            'tag_cols_for_header': ['hxl'],
        }

    def _record_last_submission_time(self, submission_stream):
        # DOCUMENTATION!!! #NOCOMMIT
        # FIXME: Mongo has only per-second resolution. Brutal.
        for submission in submission_stream:
            try:
                timestamp = submission[self.TIMESTAMP_KEY]
            except KeyError:
                pass
            else:
                timestamp = dateutil.parser.parse(timestamp)
                if (
                        self.last_submission_time is None or
                        timestamp > self.last_submission_time
                ):
                    self.last_submission_time = timestamp
            yield submission

    def _run_task(self, messages):
        # DOCUMENTATION!!! #NOCOMMIT
        source_url = self.data.get('source', False)
        if not source_url:
            raise Exception('no source specified for the export')
        source_type, source = _resolve_url_to_asset_or_collection(source_url)
        if source_type != 'asset':
            raise NotImplementedError(
                'only an `Asset` may be exported at this time')
        if not source.has_perm(self.user, 'view_submissions'):
            # Unsure if DRF exceptions make sense here since we're not
            # returning a HTTP response
            raise exceptions.PermissionDenied(
                'user cannot export this %s' % source._meta.model_name)
        if not source.has_deployment:
            raise Exception('the source must be deployed prior to export')
        export_type = self.data.get('type', '').lower()
        if export_type not in ('xls', 'csv'):
            raise NotImplementedError(
                'only `xls` and `csv` are valid export types')

        pack, submission_stream = build_formpack(source)
        # Wrap the submission stream in a generator that records the most
        # recent timestamp
        submission_stream = self._record_last_submission_time(
            submission_stream)
        options = self.build_export_options(pack)
        export = pack.export(**options)
        extension = 'xlsx' if export_type == 'xls' else export_type
        filename = self.build_export_filename(export, extension)
        self.result.save(filename, ContentFile(''))
        # FileField files are opened read-only by default and must be
        # closed and reopened to allow writing
        # https://code.djangoproject.com/ticket/13809
        self.result.close()
        self.result.file.close()
        self.result.open('wb')

        if export_type == 'csv':
            for line in export.to_csv(submission_stream):
                self.result.write(line + "\r\n")
        elif export_type == 'xls':
            # XLSX export actually requires a filename (limitation of
            # pyexcelerate?)
            with tempfile.NamedTemporaryFile(
                    prefix='export_xlsx', mode='rb'
            ) as xlsx_output_file:
                export.to_xlsx(xlsx_output_file.name, submission_stream)
                while True:
                    chunk = xlsx_output_file.read(8192)
                    if chunk:
                        self.result.write(chunk)
                    else:
                        break

        # Restore the FileField to its typical state
        self.result.close()
        self.result.open('rb')
        self.save(update_fields=['last_submission_time'])


def _b64_xls_to_dict(base64_encoded_upload):
    decoded_str = base64.b64decode(base64_encoded_upload)
    survey_dict = xls2json_backends.xls_to_dict(BytesIO(decoded_str))
    return _strip_header_keys(survey_dict)

def _strip_header_keys(survey_dict):
    for sheet_name, sheet in survey_dict.items():
        if re.search(r'_header$', sheet_name):
            del survey_dict[sheet_name]
    return survey_dict
