import React from 'react';
import PropTypes from 'prop-types';
import reactMixin from 'react-mixin';
import Reflux from 'reflux';
import autoBind from 'react-autobind';
import searches from '../searches';
import mixins from '../mixins';
import stores from '../stores';
import bem from '../bem';
import ui from '../ui';
import SearchList from '../components/searchList';
import DocumentTitle from 'react-document-title';

import {
  t,
} from '../utils';

class FormsSearchableList extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      searchContextDeployed: searches.getSearchContext('formsDeployed', {
        filterParams: {
          assetType: 'asset_type:survey',
          hasDeployment: 'has_deployment:true',
          deploymentActive: 'deployment__active:true'
        }
      }),
      searchContextDraft: searches.getSearchContext('formsDraft', {
        filterParams: {
          assetType: 'asset_type:survey',
          hasDeployment: 'has_deployment:false'
        }
      }),
      searchContextArchived: searches.getSearchContext('formsArchived', {
        filterParams: {
          assetType: 'asset_type:survey',
          hasDeployment: 'has_deployment:true',
          deploymentActive: 'deployment__active:false'
        }
      })
    };
  }
  render () {
    return (
      <DocumentTitle title={`${t('Projects')} | KoboToolbox`}>
        <FormsList {...this.state} />
      </DocumentTitle>
    );
  }
};

reactMixin(FormsSearchableList.prototype, searches.common);


class FormsList extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      deployed: 'none',
      draft: 'none',
      archived: 'none',
      totalResults: -1,
      firstLoad: true,
      fixedHeadings: '',
      fixedHeadingsWidth: 'auto'
    };
  }
  componentDidMount () {
    this.listenTo(this.props.searchContextDeployed.store, this.deployedCount);
    this.listenTo(this.props.searchContextDraft.store, this.draftCount);
    this.listenTo(this.props.searchContextArchived.store, this.archivedCount);
  }
  deployedCount (storeState) {
    this.setState({deployed: storeState.defaultQueryCount});
    this.setTotal();
  }
  draftCount (storeState) {
    this.setState({draft: storeState.defaultQueryCount});
    this.setTotal();
  }
  archivedCount (storeState) {
    this.setState({archived: storeState.defaultQueryCount});
    this.setTotal();
  }
  setTotal () {
    if (this.state.firstLoad)
      this.setState({firstLoad: false});
    if (Number.isFinite(this.state.deployed) && Number.isFinite(this.state.draft) && Number.isFinite(this.state.archived)) {
      var totalResults = this.state.deployed + this.state.draft + this.state.archived;
      this.setState({totalResults: totalResults});
    }
  }
  render () {
    return (
      <bem.List m='grouped'>
        {this.state.totalResults === 0 &&
          <bem.Loading>
            <bem.Loading__inner>
              {t("Let's get started by creating your first project. Click the New button to create a new form.")} 
            </bem.Loading__inner>
          </bem.Loading>        
        }

        <bem.AssetList m={this.state.fixedHeadings}>
{/*          <SearchList 
            searchContext={this.props.searchContextDeployed}
            name={t('Deployed')}
          />
*/}          <SearchList 
            searchContext={this.props.searchContextDraft}
            name={t('Draft')}
          />
{/*          <SearchList 
            searchContext={this.props.searchContextArchived}
            name={t('Archived')}
          />
*/}        </bem.AssetList>
      </bem.List>
    );
  }
};
reactMixin(FormsList.prototype, searches.common);
reactMixin(FormsList.prototype, Reflux.ListenerMixin);

export default FormsSearchableList;
