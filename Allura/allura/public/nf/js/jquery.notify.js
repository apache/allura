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

    function scanMessages(container, o) {
        function helper() {
            var $msg = $('.' + o.newClass + '.' + o.messageClass, container);
            if ($msg.length) {
                $msg.prepend(o.closeIcon);
                $msg.click(function(e) {
                    closer(this, o);
                });
                $msg.removeClass(o.newClass).addClass(o.activeClass);
                $msg.each(function() {
                    var self = this;
                    if (!$(self).hasClass(o.stickyClass)) {
                        var timer = $(self).attr('data-timer') || o.timer;
                        setTimeout(function() {
                            closer($(self), o);
                        }, timer);
                    }
                    $(self).fadeIn(500);
                });
            }
            setTimeout(helper, o.interval);
        }
        helper();
    }
    
    function sanitize(str) {
        return str.replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
            scanMessages(self, o);
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
        return $(this).each(function() {
            if (opts.message) {
                var o = $.metadata ? $.extend(opts, $(this).metadata()) : opts;
                if (o.sanitize) {
                    o.message = sanitize(o.message);
                    o.title = sanitize(o.title);
                }
                var html = tmpl(o.tmpl, o);
                $(this).append(html);
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
        scrollcss: { position: 'fixed', top: '20px' },
        stickyClass: 'notify-sticky',
        newClass: 'notify-new',
        activeClass: 'notify-active',
        inactiveClass: 'notify-inactive',
        messageClass: 'message',
        closeIcon: '<b title="Close" class="ico ico-close" data-icon="D"></b>'
    };
    
}(jQuery));
