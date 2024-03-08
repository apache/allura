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

/*jslint browser: true, white: false, onevar: false */
/*global jQuery, window */

(function ($) {

    /* BEGIN: John Resig's microtemplating stuff */
    var cache = {};

    function tmpl(str, data){
        var fn = !/\W/.test(str) ?
            cache[str] = cache[str] ||
            tmpl(document.getElementById(str).innerHTML) :
            new Function("obj",
                "var p=[],print=function(){p.push.apply(p,arguments);};" +
                "with(obj){p.push('" +
                str
                    .replace(/[\r\t\n]/g, " ")
                    .split("<%").join("\t")
                    .replace(/((^|%>)[^\t]*)'/g, "$1\r")
                    .replace(/\t=(.*?)%>/g, "',$1,'")
                    .split("\t").join("');")
                    .split("%>").join("p.push('")
                    .split("\r").join("\\'")
                + "');}return p.join('');");
        return data ? fn( data ) : fn;
    };
    /* END: John Resig's microtemplating stuff */

    function closer(message, o) {
        function slideComplete() {
            $(this).remove();
        }
        function fadeComplete() {
            $(this).slideUp(100, slideComplete);
        }
        $(message).animate({ opacity: 0 }, { duration: 250, queue: false, complete: fadeComplete });
    }

    function sanitize(str) {
        return str.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function displayNotification(el, o){
        var selector = '.' + o.newClass + '.' + o.messageClass;
        $(selector).fadeIn(500);
        if (!$(selector).hasClass(o.persistentClass)) {
            var timer = $(selector).attr('data-timer') || o.timer;
            setTimeout(function() {
                closer(el, o);
            }, timer);
        }
    }

    $.fn.notifier = function(options){
        var opts = $.extend({}, $.fn.notify.defaults, options);
        return $(this).each(function() {
            var self = this,
                o = $.metadata ? $.extend(opts, $(this).metadata()) : opts;
            if (o.scrollcss) {
                $(window).scroll(function() {
                    $(self).css(o.scrollcss);
                });
            }
            $('.' + o.messageClass, self).addClass(o.newClass);
            var selector = '.' + o.newClass + '.' + o.messageClass;
            $('body').on("click", selector, function(e) {
              closer(this, o);
            });
            displayNotification($(selector).get(0), o);
        });
    };

    $.fn.notify = function(msg_or_opts, options) {
        var opts;
        // For backwards compatibility
        if (typeof msg_or_opts === 'string') {
            opts = $.extend({message: msg_or_opts}, $.fn.notify.defaults, options);
        } else {
            opts = $.extend({}, $.fn.notify.defaults, msg_or_opts);
        }
        // For backwards compatibility
        if (opts.status === 'success') {
            opts.status = 'confirm';
        }
        // For compatibility with the TG default of "ok"
        if (opts.status === 'ok') {
            opts.status = 'info';
        }
        return $(this).each(function() {
            if (opts.message) {
                var o = $.metadata ? $.extend(opts, $(this).metadata()) : opts;
                if (o.sanitize) {
                    o.message = sanitize(o.message);
                    o.title = sanitize(o.title);
                }
                var html = tmpl(o.tmpl, o);
                $(this).append(html);
                var newMsgEl = $('.message:last-child', this).get(0);
                displayNotification(newMsgEl, o);
            } else {
                if (window.console) {
                    //#JSCOVERAGE_IF window.console
                    window.console.warn("No message was set in notify's config: ", o);
                    //#JSCOVERAGE_ENDIF
                }
            }
        });
    };

    $.fn.notify.defaults = {
        status: 'info',
        interval: 500,
        timer: 15000,
        sticky: false,
        title: '',
        sanitize: true,
        tmpl: '<div class="message <%=newClass%> <%=status%> <% if (sticky) { %><%=stickyClass %><% } %>" data-timer="<%=timer%>"><% if (title) { %><h6><%=title%></h6><% } %><div class="content"><%=message%></div></div>',
        stickyClass: 'notify-sticky',
		persistentClass: 'notify-persistent',
		persistentCookie: 'notify-persistent-closed',
        newClass: 'notify-new',
        activeClass: 'notify-active',
        inactiveClass: 'notify-inactive',
        messageClass: 'message',
        closeIcon: '<b title="Close" class="fa fa-close" style="float:right;"></b>'
    };

}(jQuery));
