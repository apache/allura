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
$(function() {
  var $form = $('#admin-tool-delete-modal-form');
  $('a.admin_tool_delete_modal').click(function() {
    var mount_point = $(this).data('mount-point');
    $form.find('.mount_point').val(mount_point);
    var tool_label = 'this';
    if (mount_point) {
      tool_label = 'the "' + mount_point + '"';
    }
    var msg = 'Warning: This will destroy all data in ';
    msg += tool_label;
    msg += ' tool and is irreversible!';
    $form.find('.warning-msg').text(msg);
  });
  $form.find('.delete-tool').click(function() {
    if ($form.find('.mount_point').val()) {
      $form.submit();
    } else {
      console.log('Do not know which tool to delete!');
    }
  });
});
