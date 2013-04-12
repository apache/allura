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

(function() {
    $('form[action=set_custom_fields]').submit(function(evt) {
        $(this).find('input[name^=custom_fields-][name$=label]').each(function(){
            if(this.value==''){
                evt.preventDefault();
                flash('Every custom field must have a label', 'error');
            }
        });
        $(this).find('.state-field-container').each(function() {
            $(this)
                .filter(function() {
                    return $(this).find(':input:visible[name$=type]').val() == 'milestone';
                })
                .find(':input[name^=custom_fields-][name*=milestones-][name$=".name"]').each(function() {
                    if(this.value=='') {
                        evt.preventDefault();
                        flash('Every milestone must have a name', 'error');
                    }
                });
        });
        return true;
    });
}());
