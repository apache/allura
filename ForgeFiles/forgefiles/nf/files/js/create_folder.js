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
$('#folder_id').focus();

function validateFolderForm(){
    var folder_id = document.getElementById('folder_id');
    var folder_name = $(folder_id).val().trim();
    var error = $('#error_message');

    var flag;
    flag = validateName(folder_name);

    if ( folder_name.length === 0){
        $(error).text('Please enter folder name.');
        return false;
    }
    else{
        return true;
    }
     
 }

function validateName(folder_name){
    var error = $('#error_message');
    var regular_exp = new RegExp("^[a-zA-Z0-9_ +.,=#~@!()\\[\\]-]+$");
    var validation_msg;
    if (folder_name.length === 0) {
        validation_msg = "Please enter folder name.";
    } else if (folder_name.slice(0, 1) === ".") {
        validation_msg = 'Folder name cannot start with ".".';
    } else if (folder_name.slice(0, 1) === " ") {
        validation_msg = "Folder name cannot start with a space.";
    } else if (folder_name.slice(-1) === " ") {
        validation_msg = "Folder name cannot end with a space.";
    } else if (!regular_exp.test(folder_name)) {
        validation_msg = 'Folder name cannot contain characters like ($/\"%^&*`|?<>:;).';
    } else {
        validation_msg = true;
    }
    return validation_msg;
}

$('#folder_id').keyup(function(){
    var folder_name = $('#folder_id').val();
    var error = $('#error_message');
    var flag;
    flag = validateName(folder_name);
    if (flag != true){
        $(error).text(flag);
        $('#submit_btn').attr('disabled',true);
    }
    else{
        $(error).text('');
        $('#submit_btn').attr('disabled',false);
    }
});


