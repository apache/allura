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
  function rebuild_delete_url() {
    var urls = [];
    $('.js-select-project:checked').each(function(idx, val) {
      urls.push($(val).attr('data-url'));
    });
    if (urls.length > 0) {
      var url = '/nf/admin/delete_projects/?projects=' + encodeURIComponent(urls.join('\n'));
      var url = $('<a>Delete selected projects</a>').attr('href', url);
      $('#delete-projects-url').html(url);
    } else {
      $('#delete-projects-url').text('');
    }
  }

  $('.js-select-project').change(function() {
    var shortname = $(this).attr('data-shortname');
    if ($(this).is(':checked')) {
      $('#selected-projects').append(' ' + escape_html(shortname));
    } else {
      var shortnames = $('#selected-projects').text().split(' ');
      for (var i = 0; i < shortnames.length; i++) {
        if (shortnames[i] == shortname) break;
      }
      shortnames.splice(i, 1);
      $('#selected-projects').text(shortnames.join(' '));
    }
    rebuild_delete_url();
  });

  $('tr').click(function(event) {
    if (event.target.tagName !== 'A' && event.target.type !== 'checkbox') {
      $(this).find(':checkbox').trigger('click');
    }
  });
});
