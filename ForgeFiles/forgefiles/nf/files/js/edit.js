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
$('#obj_id').select();
var obj_type = $('#obj_type').val();

function validateEditFolderForm(){
    var folder_obj = document.getElementById('obj_id');
    var folder_name = $(folder_obj).val().trim();
    var error = $('#error_message');
    var flag;
    flag = validateName(folder_name);
    if (folder_name.length === 0){
        if(obj_type == 'folder')
            $(error).text('Please enter folder name');
        else if(obj_type == 'file')
            $(error).text('Please enter file name');
        return false;
    }
    else{
        return true;
    }
     
 }

//#################//

function validateName(object_name){

    var error = $('#error_message');
    var regular_exp=new RegExp("^[a-zA-Z0-9_ +.,=#~@!()\\[\\]-]+$");
    var validation_msg;
    if(object_name.length===0){ if(obj_type == 'folder') {validation_msg="Please enter folder name."} else {validation_msg="Please enter file name."} }
    else{
        if(object_name.slice(0,1)==="."){
            if(obj_type == 'folder') {validation_msg='Folder name cannot start with ".".'} else {validation_msg='File name cannot start with ".".'} }
        else{
            if(object_name.slice(0,1)===" "){
            if(obj_type == 'folder') {validation_msg="Folder name cannot start with a space."} else {validation_msg="File name cannot start with a space."} }
            else{
                if(object_name.slice(-1)===" "){
                 if(obj_type == 'folder') {validation_msg="Folder name cannot end with a space."} else {validation_msg="File name cannot end with a space."} }
                else{if(!regular_exp.test(object_name)){
                 if(obj_type == 'folder') {validation_msg='Folder name cannot contain characters like ($/\"%^&*`|?<>:;).'}
                 else {validation_msg='File name cannot contain characters like ($/\"%^&*`|?<>:;).'} }
                else{validation_msg=true}}}}}
    
    return validation_msg;
    }

$('#obj_id').keyup(function(){
    var obj_name = $('#obj_id').val();
    var error = $('#error_message');
    var flag;
    flag = validateName(obj_name);
    if (flag != true){
        $(error).text(flag);
        $('#submit_btn').attr('disabled',true);
    }
    else{
        $(error).text('');
        $('#submit_btn').attr('disabled',false);
    }
});

