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

ASOptions = {
    maintainScrollHistory: true,
    usePjax: true,
    useHash: true,
    forceAdvancedScroll: false,
    useShowMore: true,
    useInfiniteScroll: false
}

$(function() {
    function detectFeatures() {
        var hasAPI = window.history && window.history.pushState && window.history.replaceState;
        var iOS4 = navigator.userAgent.match(/iP(od|one|ad).+\bOS\s+[1-4]|WebApps\/.+CFNetwork/);
        if (!hasAPI || iOS4) {
            ASOptions.usePjax = false;
        }
        if (!ASOptions.usePjax) {
            if (!ASOptions.useHash) {
                ASOptions.maintainScrollHistory = false;
            }
            if (!ASOptions.forceAdvancedScroll) {
                ASOptions.useShowMore = false;
                ASOptions.useInfiniteScroll = false;
            }
        }
    }

    var firstVisibleId = null;
    var oldScrollTop = null;
    var oldTop = null;
    function saveScrollPosition() {
        // Save the relative position of the first visible element of
        // interest for later restore to keep the important visible content
        // at the same viewport position before / after DOM changes.
        // TODO: This could be made more generic by making the "interesting
        // elements" selector configurable.
        var $firstVisible = $('.timeline li:in-viewport:first');
        firstVisibleId = $firstVisible.attr('id');
        oldScrollTop = $(window).scrollTop();
        oldTop = $firstVisible.offset().top;
    }

    function restoreScrollPosition() {
        // Restore the relative position of "interesting" content previously
        // saved by saveScrollPosition.
        var $window = $(window);
        var $firstVisible = $('#'+firstVisibleId);
        if (!$firstVisible.length) {
            return;
        }
        var newTop = $firstVisible.offset().top;
        var scrollTop = $window.scrollTop();
        var elemAdjustment = newTop - oldTop;
        var viewportAdjustment = scrollTop - oldScrollTop;
        $window.scrollTop(scrollTop + elemAdjustment - viewportAdjustment);
        //console.log('restoreSP', oldTop, newTop, elemAdjustment, viewportAdjustment, scrollTop, $window.scrollTop());
        $(window).trigger('scroll');
    }

    function maintainScrollHistory_pjax() {
        // Use the HTML5 history API to record page and scroll position.
        // TODO: Page changes should pushState while just scroll changes
        // should replaceState.
        var $firstVisibleActivity = $('.timeline li:in-viewport:first');
        var page = $firstVisibleActivity.data('page');
        var limit = $('.timeline').data('limit');
        var hash = $firstVisibleActivity.attr('id');
        if (page != null && limit != null && hash != null) {
            history.replaceState(null, null, '?page='+page+'&limit='+limit+'#'+hash);
        }
    }

    function maintainScrollHistory_hash() {
        // Use the location.hash to record the scroll position.
        // TODO/FIXME: This doesn't record the page for forceAdvancedPaging, and since
        // the hash history is additive (confirm?), it can require clicking Back
        // through all of your scrolling.
        var $firstVisibleActivity = $('.timeline li:in-viewport:first');
        saveScrollPosition();
        window.location.hash = $firstVisibleActivity.attr('id');  // causes jump...
        restoreScrollPosition();
    }

    var delayed = null;
    function scrollHandler(event) {
        clearTimeout(delayed);
        var method = ASOptions.usePjax
            ? maintainScrollHistory_pjax
            : maintainScrollHistory_hash;
        var delay = ASOptions.usePjax
            ? 100   // scrolls replace history and don't affect scrolling, so more is ok
            : 750;  // scrolls add history and affect scrolling, so make sure they're done
        delayed = setTimeout(method, delay);
    }

    function enableScrollHistory() {
        // Attempt to record the scroll position in the browser history
        // using either the HTML5 history API (aka PJAX) or via the location
        // hash.  Otherwise, when the user clicks a link and then comes back,
        // they will lose their scroll position and, in the case of advanced
        // paging, which page they were on.  See: http://xkcd.com/1309/
        if (!ASOptions.maintainScrollHistory) {
            return;
        }
        $(window).scroll(scrollHandler);
    }

    function pageOut(newer) {
        // Remove a single page of either newer or older content.
        var $timeline = $('.timeline li');
        var limit = $('.timeline').data('limit');
        var range = newer ? [0, limit] : [-limit, undefined];
        $timeline.slice(range[0], range[1]).remove();
        $('.no-more.'+(newer ? 'newer' : 'older')).remove();
    }

    function pageIn(newer, url) {
        // Load a single page of either newer or older content from the URL.
        // If the added page causes too many to be on screen, calls pageOut
        // to keep memory usage in check.  Also uses save/restoreScrollPosition
        // to try to keep the same content in view at the same place.
        $.get(url, function(html) {
            var $html = $(html);
            var $timeline = $('.timeline');
            var limit = $('.timeline').data('limit');
            saveScrollPosition();
            if ($html.length < limit) {
                var method = newer ? 'before' : 'after';
                var cls = newer ? 'newer' : 'older';
                $timeline[method]('<div class="no-more '+cls+'">No more activities</div>');
            }
            var method = newer ? 'prepend' : 'append';
            $timeline[method]($html);
            var firstPage = $('.timeline li:first').data('page');
            var lastPage = $('.timeline li:last').data('page');
            if (lastPage - firstPage >= 3) {
                pageOut(!newer);
            }
            if (ASOptions.useShowMore) {
                // this has to be here instead of showMoreLink handler to
                // ensure that scroll changes between added / removed content
                // and Show More links combine properly and don't cause a jump
                // due to hitting the edge of the page
                updateShowMore();
            }
            restoreScrollPosition();
        }).fail(function() {
            flash('Error loading activities', 'error');
        });
    }

    function makeShowMoreLink(newer, targetPage, limit) {
        var $link = $('<a class="show-more">Show More</a>');
        $link.addClass(newer ? 'newer' : 'older');
        $link.attr('href', 'pjax?page='+targetPage+'&limit='+limit);
        $link.click(function(event) {
            event.preventDefault();
            pageIn(newer, this.href);
        });
        return $link;
    }

    function updateShowMore() {
        // Update the state of the Show More links when using "Show More"-style
        // advanced paging.
        var $timeline = $('.timeline');
        if (!$timeline.length) {
            return;
        }
        var limit = $('.timeline').data('limit');
        var firstPage = $('.timeline li:first').data('page');
        var lastPage = $('.timeline li:last').data('page');
        var noMoreNewer = firstPage == 0 || $('.no-more.newer').length;
        var noMoreOlder = $('.no-more.older').length;
        $('.show-more').remove();  // TODO: could update HREFs instead of always re-creating links
        if (!noMoreNewer) {
            $timeline.before(makeShowMoreLink(true, firstPage-1, limit));
        }
        if (!noMoreOlder) {
            $timeline.after(makeShowMoreLink(false, lastPage+1, limit));
        }
    }

    function enableShowMore() {
        $('.page_list').remove();
        updateShowMore();
    }

    function enableInfiniteScroll() {
    }

    function enableAdvancedPaging() {
        if (ASOptions.useInfiniteScroll) {
            enableInfiniteScroll();
        } else if (ASOptions.useShowMore) {
            enableShowMore();
        }
    }

    detectFeatures();
    enableScrollHistory();
    enableAdvancedPaging();
});

function markTop() {
    var $marker = $('#offset-marker');
    if (!$marker.length) {
        $marker = $('<div id="offset-marker">&nbsp;</div>');
        $marker.css({
            'position': 'absolute',
            'top': 0,
            'width': '100%',
            'border-top': '1px solid green'
        });
        $marker.appendTo($('body'));
    }
    $marker.css({'top': $(window).scrollTop()});
}

function markFirst() {
    $('.timeline li:in-viewport:first').css({'background-color': '#f0fff0'});
}
