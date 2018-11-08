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

// Reaction support

$(function(){

$('.reaction-button').tooltipster({
    animation: 'fade',
    delay: 200,
    theme: 'tooltipster-default',
    trigger: 'click',
    position: 'top',
    iconCloning: false,
    maxWidth: 400,
    contentAsHTML: true,
    interactive: true,
    functionReady: function(instance, helper) {
        $(helper).find('.emoji_button').click(function() {
            reactComment(instance, $(this).data('emoji'));
        });
    }
});

$('.reaction-button').each(function() {
    var btnId = $(this).attr('id');
    $(this).click(function(e) {
        e.preventDefault();

        var emohtml = '';
        for(var emo in global_reactions) {
            emohtml += '<span class=\'emoji_button\' data-emoji=\'' + emo + '\'>' + 
            twemoji.parse(global_reactions[emo]) + '</span>';
        }
        var tooltiptext = '<div class="post-reactions-list">' + emohtml + '</div>';
        $(this).tooltipster('content', tooltiptext);
        $(this).tooltipster('show');
    });
});


});

function reactComment(btn ,r) {
var reacts_list = btn.closest('.post-content').find('.reactions');
$.ajax({
    type: 'post',
    url: btn.data('commentlink') + 'post_reaction',
    data: {
        'r' : r,
        '_session_id' : $.cookie('_session_id')
    },
    success: function(res) {
        var react_html = '';

        for (var i in res.counts) {
            react_html += '<span>' + global_reactions[i] + '</span> ' + res.counts[i];
        }
        
        reacts_list.html(react_html);
        twemoji.parse(reacts_list[0]);
        btn.tooltipster('hide');
    }
});
}