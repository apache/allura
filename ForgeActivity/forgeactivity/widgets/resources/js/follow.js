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
        $.get(this.href, function(result) {
            flash(result.message, result.success ? 'success' : 'error');
            console.log(result.following);
            if (result.following && !$link.hasClass('active')) {
                $link.attr('href', $link.attr('href').replace(/True$/i, 'False'));
                $link.addClass('active');
                title_stop_following($link);
                title_stop_following($link.find('b'));
            } else if (!result.following && $link.hasClass('active')) {
                $link.attr('href', $link.attr('href').replace(/False$/i, 'True'));
                $link.removeClass('active');
                title_start_following($link);
                title_start_following($link.find('b'));
            }
        });
        return false;
    });
});
