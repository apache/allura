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

$('#admin_modal_title').hide();
$('#remarks_id').focus();


 function ConfirmPublishFolder(){
     var remarks = document.getElementById('remarks_id');
     var release_notes = $(remarks).val().trim();
     var error = $('#error_message');
     var parent = document.getElementById('parent_publish_status');
     var parent_publish_status = $(parent).val();
     var current_folder = document.getElementById('publish_status');
     var publish_status = $(current_folder).val();
     var submit_btn = $('#submit_btn');
     if(release_notes.length === 0){
        $(error).text('Please enter release notes');
        return false;
     }
     else if(parent_publish_status === 'False'){
        $(submit_btn).attr('disabled', true);
        $(error).text('To publish this folder, please link a file under it to the Download button');
        return false;
     }
     else{
        return true;
    }

 }
