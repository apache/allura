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

$(document).ready(function() {
    function title_stop_following($elem) {
        $elem.attr('title', $elem.attr('title').replace(/^([A-Z])(\w+)/, function(p,c,w) {
            return 'Stop ' + c.toLowerCase() + w + 'ing';
        }));
    }

    function title_start_following($elem) {
        $elem.attr('title', $elem.attr('title').replace(/^Stop ([a-z])(\w+)ing/, function(p,c,w) {
            return c.toUpperCase() + w;
        }));
    }

    $('.artifact_follow').click(function(e) {
        e.preventDefault();
        var $link = $(this);
        var data = {
            '_session_id': $link.data('csrf'),
            'follow': ! $link.data('following')
        };
        $.post(this.href, data, function(result) {
            flash(result.message, result.success ? 'success' : 'error');
            $link.data('following', result.following);
            if (result.following && !$link.hasClass('active')) {
                $link.addClass('active');
                title_stop_following($link);
                title_stop_following($link.find('b'));
            } else if (!result.following && $link.hasClass('active')) {
                $link.removeClass('active');
                title_start_following($link);
                title_start_following($link.find('b'));
            }
        });
        return false;
    });
});
