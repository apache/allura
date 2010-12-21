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
            $(this).animate({ height: 0, border: 0, padding: 0, margin: 0 }, { duration: 100, queue: false, complete: slideComplete });
        }
        $(message).animate({ opacity: 0 }, { duration: 250, queue: false, complete: fadeComplete });
    }

    function scanMessages(container, o) {
        function helper() {
            var $msg = $('.' + o.newClass + '.' + o.messageClass, container);
            $msg.prepend(o.closeIcon);
            $msg.click(function(e) {
                e.preventDefault();
                closer(this, o);
            });
            $msg.fadeIn(500, function() {
                var self = this;
                $(self).removeClass(o.newClass).addClass(o.activeClass);
                if (!$(self).hasClass(o.stickyClass)) {
                    var timer = $(self).attr('data-timer') || o.timer;
                    setTimeout(function() {
                        closer(self, o);
                    }, timer);
                }
            });
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
            $.fn.notifier.element = self;
            if (o.scrollcss) {
                $(window).scroll(function() {
                    $(self).css(o.scrollcss);
                }); 
            }
            $('.' + o.messageClass, self).addClass(o.newClass);
            scanMessages(self, o);
        });
    };
    
    $.fn.notify = function(msg, options) {
        var opts = $.extend({message: msg}, $.fn.notify.defaults, options);
        return $(this).each(function() {
            if (msg) {
                var o = $.metadata ? $.extend(opts, $(this).metadata()) : opts;
                if (o.sanitize) {
                    o.message = sanitize(o.message);
                    o.title = sanitize(o.title);
                }
                var html = tmpl(o.tmpl, o);
                $($.fn.notifier.element).append(html);
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
        tmpl: '<section class="message <%=newClass%> <%=status%> <% if (sticky) { %><%=stickyClass %><% } %>" data-timer="<%=timer%>"><% if (title) { %><header><%=title%></header><% } %><div class="content"><%=message%><div></section>',
        scrollcss: { position: 'fixed', top: '20px' },
        stickyClass: 'notify-sticky',
        newClass: 'notify-new',
        activeClass: 'notify-active',
        inactiveClass: 'notify-inactive',
        messageClass: 'message',
        closeIcon: '<b title="Close" class="ico ico-close" data-icon="D"></b>'
    };
    
}(jQuery));
