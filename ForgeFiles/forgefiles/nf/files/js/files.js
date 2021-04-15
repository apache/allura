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

$.ajaxPrefilter(function( options, originalOptions, jqXHR ) {    options.async = true; });

function removeModalContent(){
    $('#delete_folder').val(' ');
    $('#error_message_delete_folder').remove();
}

var cval = $.cookie('_session_id');

 function ConfirmDisableFolder(folderID,status,parent_status,url)
     {
         if (status == 'True' && parent_status == 'True'){
             alert('Please enable parent folder of this folder');
             return false;
         }
         else{
             if (status == 'False'){
                 var confirm_resp = confirm("Are you sure you want to disable?");
                 var disable_status = 'True';
             }
             else if(status == 'True'){
                 var confirm_resp = confirm("Are you sure you want to enable?");
                 var disable_status = 'False';
             }
             if (confirm_resp){
                $.post(url, {'folder_id':folderID, 'status':disable_status, _session_id:cval}, function() {
                    location.reload();
                });
             }
             else
                 return false;
            true
         }
     }
 function ConfirmDisableFile(fileID,status,parent_status,url)
     {
         if (status == 'True' && parent_status == 'True'){
             alert('Please enable parent folder of this file');
             return false;
         }
         else{
             if (status == 'False'){
                 var confirm_resp = confirm("Are you sure you want to disable?");
                 var disable_status = 'True';
             }
             else if(status == 'True'){
                 var confirm_resp = confirm("Are you sure you want to enable?");
                 var disable_status = 'False';
             }
             if (confirm_resp){
                 $.post(url, {'file_id':fileID, 'status':disable_status, _session_id:cval}, function() {
                    location.reload();
                });
             }
             else
                 return false;
         }
     }

 function ConfirmLinkFile(fileID,linked_to_download,url)
 {
     
    if(linked_to_download === 'True'){
        var confirm_resp = confirm("This file is already linked to Downloads. Do you want to unlink it?");
        var link_status = 'False';
    }
    else{
        var confirm_resp = confirm("Are you sure you want to link to the Downloads?");
        var link_status = 'True';
    }
    $.post(url, {'file_id':fileID, 'status':link_status, _session_id:cval}, function() {
        location.reload();
    })
 }


