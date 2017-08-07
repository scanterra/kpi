import React from 'react';
import PropTypes from 'prop-types';
import reactMixin from 'react-mixin';
import autoBind from 'react-autobind';
import Reflux from 'reflux';

import searches from '../searches';
import mixins from '../mixins';
import stores from '../stores';
import {dataInterface} from '../dataInterface';
import bem from '../bem';
import AssetRow from './assetrow';
import $ from 'jquery';

import {
  parsePermissions,
  t,
} from '../utils';

class SearchList extends Reflux.Component {
  constructor(props) {
    super(props);
    var selectedCategories = {
      'Draft': true,
      'Deployed': true, 
      'Archived': true
    };
    this.state = {
      selectedCategories: selectedCategories,
      ownedCollections: [],
      fixedHeadings: '',
      fixedHeadingsWidth: 'auto'
    };
    this.store = stores.selectedAsset;
    autoBind(this);
  }
  componentDidMount () {
    this.searchDefault();
    this.listenTo(this.searchStore, this.searchChanged);
  }
  searchChanged (searchStoreState) {
    this.setState(searchStoreState);
  }

  renderAssetRow (resource) {
    var currentUsername = stores.session.currentAccount && stores.session.currentAccount.username;
    var perm = parsePermissions(resource.owner, resource.permissions);
    var isSelected = stores.selectedAsset.uid === resource.uid;
    var ownedCollections = this.state.ownedCollections;

    return (
        <this.props.assetRowClass key={resource.uid}
                      currentUsername={currentUsername}
                      perm={perm}
                      onActionButtonClick={this.onActionButtonClick}
                      isSelected={isSelected}
                      ownedCollections={ownedCollections}
                      deleting={resource.deleting}
                      {...resource}
                        />
      );
  }
  renderHeadings () {
    return [
      (
        <bem.List__heading key='1'>
          <span className={this.state.parentName ? 'parent' : ''}>{t('My Library')}</span>
          {this.state.parentName &&
            <span>
              <i className="k-icon-next" />
              <span>{this.state.parentName}</span>
            </span>
          }
        </bem.List__heading>
      ),
      (
        <bem.AssetListSorts className="mdl-grid" key='2'>
          <bem.AssetListSorts__item m={'name'} className="mdl-cell mdl-cell--8-col mdl-cell--4-col-tablet mdl-cell--2-col-phone">
            {t('Name')}
          </bem.AssetListSorts__item>
          <bem.AssetListSorts__item m={'owner'} className="mdl-cell mdl-cell--2-col mdl-cell--2-col-tablet mdl-cell--1-col-phone">
            {t('Owner')}
          </bem.AssetListSorts__item>
          <bem.AssetListSorts__item m={'modified'} className="mdl-cell mdl-cell--2-col mdl-cell--2-col-tablet mdl-cell--1-col-phone">
            {t('Last Modified')}
          </bem.AssetListSorts__item>
        </bem.AssetListSorts>
      )];
  }
  renderGroupedHeadings () {
    return (
        <bem.AssetListSorts className="mdl-grid" style={{width: this.state.fixedHeadingsWidth}}>
          <bem.AssetListSorts__item m={'name'} className="mdl-cell mdl-cell--5-col mdl-cell--4-col-tablet mdl-cell--2-col-phone">
            {t('Name')}
          </bem.AssetListSorts__item>
          <bem.AssetListSorts__item m={'owner'} className="mdl-cell mdl-cell--2-col mdl-cell--1-col-tablet mdl-cell--hide-phone">
            {t('Shared by')}
          </bem.AssetListSorts__item>
          <bem.AssetListSorts__item m={'created'} className="mdl-cell mdl-cell--2-col mdl-cell--hide-tablet mdl-cell--hide-phone">
            {t('Created')}
          </bem.AssetListSorts__item>
          <bem.AssetListSorts__item m={'modified'} className="mdl-cell mdl-cell--2-col mdl-cell--2-col-tablet mdl-cell--1-col-phone">
            {t('Last Modified')}
          </bem.AssetListSorts__item>
          <bem.AssetListSorts__item m={'submissions'} className="mdl-cell mdl-cell--1-col mdl-cell--1-col-tablet mdl-cell--1-col-phone" >
              {t('Submissions')}
          </bem.AssetListSorts__item>
        </bem.AssetListSorts>
      );
  }
  renderGroupedResults () {
    var searchResultsBucket = 'defaultQueryResultsList';
    // if (this.state.searchResultsDisplayed)
    //   searchResultsBucket = 'searchResultsCategorizedResultsLists';

    return (
    	<div>
	      <bem.List__subheading>
	        {this.props.name}
	      </bem.List__subheading>
	      <bem.AssetItems>
	        {this.renderGroupedHeadings()}
	        {
	          (()=>{
	            return this.state[searchResultsBucket].map(
	              this.renderAssetRow)
	          })()
	        }
	      </bem.AssetItems>
     	</div> 
    );
  }

  render () {
    var queryState = this.state.defaultQueryState;
    var queryCount = this.state.defaultQueryCount;
    if (this.state.searchResultsDisplayed) {
    	queryState = this.state.searchState;
    	queryCount = this.state.searchQueryCount;
    }

		switch (queryState) {
	    case 'done':
	      if (queryCount < 1) {
	      	return false;
	      } else {
	    		return this.renderGroupedResults();
	      }
	    break;
	    case undefined: 
        return (
          <bem.Loading>
            <bem.Loading__inner>
              <i />
              {t('loading' + ' ' + this.props.name)} 
            </bem.Loading__inner>
          </bem.Loading>
        );
	    default:
	    	return false;
		}

  }
};

SearchList.defaultProps = {
  assetRowClass: AssetRow,
  searchContext: 'default',
  name: ''
};

SearchList.contextTypes = {
  router: PropTypes.object
};

reactMixin(SearchList.prototype, searches.common);
reactMixin(SearchList.prototype, mixins.clickAssets);
reactMixin(SearchList.prototype, Reflux.ListenerMixin);

export default SearchList;
