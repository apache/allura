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

(function () {
    $('div.discussion-post').each(function () {
        var post = this;
        $('.moderate_post', post).click(function(e){
            e.preventDefault();
            var mod = $(this).text();

            if ($(this).hasClass('delete')) mod = 'Delete';
            else if ($(this).hasClass('approve')) mod = 'Approve';
            else if ($(this).hasClass('spam')) mod = 'Spam';
            else if ($(this).hasClass('undo')) mod = 'Undo';


            if (mod === 'Delete' && !confirm('Really delete this post?')) {
                return;
            }
            $.ajax({
                type: 'POST',
                url: this.parentNode.action,
                data: jQuery(this.parentNode).serialize(),
                success: function() {
                    if (mod === 'Delete'){
                        $(post).remove();
                    }
                    else if (mod === 'Approve'){
                        $('a.shortlink, form.moderate_spam, form.moderate_approve', post).toggle();
                        $('div.moderate', post).removeClass('moderate');
                    }
                    else if (mod == 'Spam'){
                        spam_block_display($(post), 'show_spam');
                    }
                    else if (mod == 'Undo'){
                        spam_block_display($(post), 'hide_spam');
                    }
                },
                error: function() {
                    flash('Oops, something went wrong.', 'error')
                },
            });
        });

        $('.spam-all-block', post).click(function(e) {
            e.preventDefault();
            var $this = $(this);
            var cval = $.cookie('_session_id');
            $.ajax({
                type: 'POST',
                url: $this.attr('data-admin-url') + '/block_user',
                data: {
                    username: $this.attr('data-user'),
                    perm: 'post',
                    '_session_id': cval
                },
                success: function (data, textStatus, jqxhr) {
                    if (data.error) {
                        flash(data.error, 'error');
                    } else if (data.username) {
                        flash('User blocked', 'success');
                        // full page form submit
                        $('<form method="POST" action="' + $this.data('discussion-url')+'moderate/save_moderation_bulk_user?username=' + $this.attr('data-user') + '&spam=1">' +
                            '<input name="_session_id" type="hidden" value="'+cval+'"></form>')
                            .appendTo('body')
                            .submit();
                    } else {
                        flash('Error.  Make sure you are logged in still.', 'error');
                    }
                },
                error: function() {
                    flash('Oops, something went wrong.', 'error')
                },
            });
        });

        function spam_block_display($post, display_type) {
            var spam_block = $post.find('.info.grid-15.spam-present');
            var row = $post.find('.comment-row').eq(0);

            if (display_type == 'show_spam') {
                spam_block.show();
                row.hide();
            } else if (display_type == 'hide_spam') {
                spam_block.hide();
                row.show();
            }
        }

        if($('a.edit_post', post)){
            $('a.edit_post', post).click(function (evt) {
                evt.preventDefault();
                $('.display_post', post).hide();

                // remove the options column, but have to adjust the width of the middle section which is
                // already hard-coded
                var $opts = $('.options:first', post);
                var opts_width = $opts.outerWidth(true);
                $opts.hide();
                var $post_middle = $('div.grid-14:first', post);
                $post_middle.data('original-width', $post_middle.width());
                $post_middle.width($post_middle.width() + opts_width);

                var $edit_post_form = $('.edit_post_form', post);
                var cm = get_cm($edit_post_form);
                $edit_post_form.show();
                cm.refresh();
                cm.focus();
            });
            $("a.cancel_edit_post", post).click(function(evt){
                $('.display_post', post).show();
                $('.options', post).show();
                $('.edit_post_form', post).hide();
                var $post_middle = $('div.grid-14:first', post);
                $post_middle.width($post_middle.data('original-width'));
            });
        }
        if($('.reply_post', post)){
            $('.reply_post', post).click(function (evt) {
                evt.preventDefault();
                var $reply_post_form = $('.reply_post_form', post);
                var cm = get_cm($reply_post_form);
                $reply_post_form.show();
                cm.focus();
                $('form', $reply_post_form).trigger('replyRevealed');
            });
        }
        if($('.add_attachment', post)){
            $('.add_attachment', post).click(function (evt) {
                evt.preventDefault();
                $('.add_attachment_form', post).show();
            });
        }
        if($('.shortlink', post)){
            var popup = $('.shortlink_popup', post);
            $('.shortlink', post).click(function(evt){
                evt.preventDefault();
                popup.lightbox_me({
                    onLoad: function() {
                        $('input', popup).select();
                    }
                });
            });
            $('.close', popup).on('click', function() {
                popup.hide();
            });
        }
    });
}());