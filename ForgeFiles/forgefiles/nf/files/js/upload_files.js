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

function validateFileForm() {
    var file_input = document.getElementById('file_input');
    var file_path = file_input.value.split('\\').pop();
    var filename = $('#filename');
    var file_val = $(file_input).val();
    var error = $('#error_message');
    if (file_val.length === 0) {
        $(error).text('Please upload a file');
        return false;
    } else {
        $(filename).val(file_path);
        return true;
    }
}
