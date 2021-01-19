/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/

var dom = React.createElement;
var grid = 'grid-8';

/* top-level form state */
var state = {
  'step': 'verify',       // 'verify' (enter number) or 'check' (enter pin)
  'in_progress': false,   // API call in progress
  'error': null,          // error, returned from previous API call
  'number': null,         // phone number, entered  by user on 'verify' step
  'pin': null,            // PIN, entered  by user on 'check' step
};


function set_state(new_state) {
  /* Set state and re-render entire UI */
  for (var key in new_state) {
    state[key] = new_state[key];
  }
  render(state);
}

function render(state) {
  /* Mount top-level component into the DOM */
  ReactDOM.render(
    dom(PhoneVerificationForm, {state: state}),
    document.getElementById('phone-verification-form')
  );
}

var FormStepMixin = {

  /*
   * Subclasses must implement:
   *   - getAPIUrl(): return API url this step will submit to
   *   - getAPIData(): returns data to submit to API url
   *   - getLabel(): returns label text for the input
   *   - getKey(): returns key in the global state, which will be updated by the input
   *   - onSuccess(resp): callback wich will be called after successful call to API
   */

  render: function() {
    var input_props = {
      type: 'text',
      ref: 'mainInput',
      className: grid,
      value: this.props.state[this.getKey()] || '',
      disabled: this.isInputDisabled(),
      onChange: this.handleChange,
      onKeyDown: this.onKeyDown,
      autoFocus: true
    };
    var button_props = {
      onClick: this.handleClick,
      disabled: this.isButtonDisabled()
    };
    return dom('div', null,
             dom('div', {className: grid,
                         dangerouslySetInnerHTML: this.getMessage()}),
             dom('div', {className: grid,
                         dangerouslySetInnerHTML: this.getExtraMessage()}),
             dom('label', {className: grid}, this.getLabel()),
             dom('input', input_props),
             dom('div', {className: grid + ' error-text',
                         dangerouslySetInnerHTML: this.getErrorHtml()}),
             dom('div', {className: grid},
               dom('button', button_props, 'Submit')));
  },

  componentDidMount: function() {
    ReactDOM.findDOMNode(this.refs.mainInput).focus();
  },
  componentDidUpdate: function() {
    ReactDOM.findDOMNode(this.refs.mainInput).focus();
  },

  getErrorHtml: function() {
    return {__html: this.props.state.error || '&nbsp;'};
  },

  getHtml: function(elem_id) {
    var html = document.getElementById(elem_id).innerHTML;
    return {__html: html};
  },

  getMessage: function() { return this.getHtml('message-' + this.getKey()); },
  getExtraMessage: function() { return this.getHtml('message-extra'); },

  handleClick: function() {
    if (!this.isButtonDisabled()) {
      set_state({error: null});
      this.callAPI();
    }
  },

  handleChange: function(event) {
    var new_state = {};
    new_state[this.getKey()] = event.target.value;
    set_state(new_state);
  },

  onKeyDown: function(event) {
    if (event.key == 'Enter') {
      this.handleClick();
    }
  },

  isInputDisabled: function() { return this.props.state.in_progress; },

  isButtonDisabled: function() {
    var input = this.props.state[this.getKey()];
    var has_input = Boolean(input);
    return this.isInputDisabled() || !has_input;
  },

  callAPI: function() {
    var url = this.getAPIUrl();
    var data = this.getAPIData();
    var csrf = $.cookie('_session_id');
    data._session_id = csrf;
    set_state({in_progress: true});
    $.post(url, data, function(resp) {
      if (resp.status == 'ok') {
        this.onSuccess(resp);
      } else {
        set_state({error: resp.error});
      }
    }.bind(this)).fail(function(xhr) {
      var error = 'Request to API failed, please try again';
      if (xhr.status === 401) {
        error = 'Authentication issue.  Please <a href="/p/add_project" target=_top>reload the page</a> and make sure you are logged in.';
      }
      set_state({error: error});
    }).always(function() {
      set_state({in_progress: false});
    });
  }
};


var StepVerify = React.createClass({
  mixins: [FormStepMixin],

  getAPIUrl: function() { return 'verify_phone'; },
  getAPIData: function() { return {'number': this.props.state[this.getKey()]}; },
  getLabel: function() { return 'Enter phone number'; },
  getKey: function() { return 'number'; },
  onSuccess: function() { set_state({step: 'check'}); }
});

var StepCheck = React.createClass({
  mixins: [FormStepMixin],

  getAPIUrl: function() { return 'check_phone_verification'; },
  getAPIData: function() { return {'pin': this.props.state[this.getKey()]}; },
  getLabel: function() { return 'Enter your PIN'; },
  getKey: function() { return 'pin'; },
  onSuccess: function() {
    var form = window.top.jQuery('form[action="/p/register"]');
    form.submit();
  }
});

var PhoneVerificationForm = React.createClass({
  /*
   * Top-level component for phone verification form
   * Used as controller, to render proper form step.
   */
  render: function() {
    var step = this.props.state.step;
    if (step == 'verify') {
        return dom(StepVerify, {state: this.props.state});
    } else if (step == 'check') {
        return dom(StepCheck, {state: this.props.state});
    }
  }
});

render(state);  // initial render
