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

function ConfirmDeleteFolder() {
    var obj_id = document.getElementById('delete_id');
    var confirm_delete = $(obj_id).val();
    var error = $('#error_message');
    if (confirm_delete === "DELETE") {
        return true;
    } else {
        $(error).text('You must confirm with the word DELETE');
        return false;
    }
}
