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

$(function(){
    $form = $('#update-values');
    if ($form.length == 0) {
        $form = $('.editbox > form');
    }
    if ($('#id_search').length == 0) {
        $form.append('<input type="hidden" name="__search" id="id_search">');
    }
    $('#id_search').val(window.location.search);
    $('#assigned_to').val('');
    $('#select_all').click(function(){
        if(this.checked){
            $('tbody.ticket-list input[type=checkbox]').prop('checked', true);
        }
        else{
            $('tbody.ticket-list input[type=checkbox]').prop('checked', false);
        }
    });
    $form.submit(function(){
        var $checked=$('tbody.ticket-list input:checked'), count=$checked.length;

        if ( !count ) {
            $('#result').text('No tickets selected.');
            return false;
        }

        $checked.each(function() {
            $form.append('<input type="hidden" name="__ticket_ids" value="'+$(this).val()+'"/>');
        });
    });
});
