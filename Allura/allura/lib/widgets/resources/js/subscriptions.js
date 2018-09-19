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

/* top-level form state */
var state = {
  'thing': 'tool',
  'subscribed': false,
  'url': '',
  'icon': {}
};

SubscriptionForm = React.createClass({

  getInitialState: function() {
    return {tooltip_timeout: null};
  },

  render: function() {
    var action = this.props.subscribed ? "Unsubscribe from" : "Subscribe to";
    var title = action + ' this ' + this.props.thing;
    var opts = {
      ref: 'link',
      className: this.props.icon.css + (this.props.subscribed ? ' active' : ''),
      href: '#',
      title: title,
      onClick: this.handleClick
    };
    if (this.props.in_progress) {
      opts.style = {cursor: 'wait'};
    }
    return dom('a', opts);
  },

  handleClick: function(e) {
    e.preventDefault();
    var url = this.props.url;
    var csrf = $.cookie('_session_id');
    var data = {_session_id: csrf};
    if (this.props.subscribed) {
      data.unsubscribe = true;
    } else {
      data.subscribe = true;
    }
    set_state({in_progress: true});
    $.post(url, data, function(resp) {
      if (resp.status == 'ok') {
        set_state({
          subscribed: resp.subscribed,
        });
        var text = null;
        var msgStat = null;
        if (resp.subscribed_to_tool) {
          msgStat = 'error';
          text = "You can't subscribe to this ";
          text += this.props.thing;
          text += " because you are already subscribed to the entire ";
          text += resp.subscribed_to_entire_name ? resp.subscribed_to_entire_name : "tool";
          text += ".";
        } else {
          msgStat = 'info';
          var action = resp.subscribed ? 'subscribed to' : 'unsubscribed from';
          text = 'Successfully ' + action + ' this ' + this.props.thing + '.';
        }
        $('#messages').notify(text, {status: msgStat});
      }
    }.bind(this)).always(function() {
      set_state({in_progress: false});
    });
    return false;
  },

  getLinkNode: function() { return ReactDOM.findDOMNode(this.refs.link); },

  componentDidMount: function() {
    var link = this.getLinkNode();
    $(link).tooltipster({
      content: null,
      animation: 'fade',
      delay: 200,
      trigger: 'hover',
      position: 'top',
      iconCloning: false,
      maxWidth: 300
    });
  }

});

function set_state(new_state) {
  /* Set state and re-render entire UI */
  for (var key in new_state) {
    state[key] = new_state[key];
  }
  render(state);
}

function render(state) {
  var props = {};
  for (var key in state) { props[key] = state[key]; }
  ReactDOM.render(
    dom(SubscriptionForm, props),
    document.getElementById('subscription-form')
  );
}

$(function() {
  set_state(document.SUBSCRIPTION_OPTIONS);
});
