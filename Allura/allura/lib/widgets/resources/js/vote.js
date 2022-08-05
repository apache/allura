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

$(document).ready(function() {
  function vote(vote) {
    var $form = $('#vote form');
    var url = $form.attr('action');
    var method = $form.attr('method');
    var _session_id = $form.find('input[name="_session_id"]').val();
    $.ajax({
      url: url,
      type: method,
      data: {
        vote: vote,
        _session_id: _session_id
      },
      success: function(data) {
        if (data.status == 'ok') {
          $('#vote .votes-up').text(data.votes_up);
          $('#vote .votes-down').text(data.votes_down);
          $('#vote .votes-percent').text(data.votes_percent);
          var $vote_up = $('#vote .js-vote-up');
          var $vote_down = $('#vote .js-vote-down');
          if (vote === 'u') {
            $vote_up.toggleClass('active');
            $vote_down.removeClass('active');
          } else if (vote === 'd') {
            $vote_down.toggleClass('active');
            $vote_up.removeClass('active');
          }
        }
      }
    });
  }

  $('#vote .js-vote-up').click(function(event) {
    event.preventDefault();
    vote('u');
  });
  $('#vote .js-vote-down').click(function(event) {
    event.preventDefault();
    vote('d');
  });
});
