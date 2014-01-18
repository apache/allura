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

ActivityBrowseOptions = {
    maintainScrollState: true,
    usePjax: true,
    useHash: true,
    forceAdvancedScroll: false,
    useShowMore: true,
    useInfiniteScroll: false
}

$(function() {
    var hasAPI = window.history && window.history.pushState && window.history.replaceState;
    var iOS4 = navigator.userAgent.match(/iP(od|one|ad).+\bOS\s+[1-4]|WebApps\/.+CFNetwork/);
    if (!hasAPI || iOS4) {
        ActivityBrowseOptions.usePjax = false;
    }
    if (!ActivityBrowseOptions.usePjax) {
        if (!ActivityBrowseOptions.useHash) {
            ActivityBrowseOptions.maintainScrollState = false;
        }
        if (!ActivityBrowseOptions.forceAdvancedScroll) {
            ActivityBrowseOptions.useShowMore = false;
            ActivityBrowseOptions.useInfiniteScroll = false;
        }
    }

    var firstVisibleId = null;
    var oldScrollTop = null;
    var oldTop = null;
    function saveScrollPosition() {
        var $firstVisible = $('.timeline li:in-viewport:first');
        firstVisibleId = $firstVisible.attr('id');
        oldScrollTop = $(window).scrollTop();
        oldTop = $firstVisible.offset().top;
    }
    function restoreScrollPosition() {
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

    function maintainScrollState_pjax() {
        var $firstVisibleActivity = $('.timeline li:in-viewport:first');
        var page = $firstVisibleActivity.data('page');
        var limit = $('.timeline').data('limit');
        var hash = $firstVisibleActivity.attr('id');
        if (page != null && limit != null && hash != null) {
            history.replaceState(null, null, '?page='+page+'&limit='+limit+'#'+hash);
        }
    }

    function maintainScrollState_hash() {
        var $firstVisibleActivity = $('.timeline li:in-viewport:first');
        saveScrollPosition();
        window.location.hash = $firstVisibleActivity.attr('id');  // causes jump...
        restoreScrollPosition();
    }

    var delayed = null;
    function scrollHandler(event) {
        clearTimeout(delayed);
        delayed = setTimeout(ActivityBrowseOptions.usePjax
            ? maintainScrollState_pjax
            : maintainScrollState_hash, 100);
    }

    function maintainScrollState() {
        if (!ActivityBrowseOptions.maintainScrollState) {
            return;
        }
        $(window).scroll(scrollHandler);
    }

    function pageOut(newer) {
        var $timeline = $('.timeline li');
        var limit = $('.timeline').data('limit') || 100;
        var range = newer ? [0, limit] : [-limit, undefined];
        $timeline.slice(range[0], range[1]).remove();
        if (!newer && $('.show-more.older').hasClass('no-more')) {
            $('.no-more').removeClass('no-more');
            updateShowMore();
        }
    }
    window.pageOut = pageOut;

    function pageIn(newer, url) {
        $.get(url, function(html) {
            saveScrollPosition();
            if (newer) {
                $('.timeline').prepend(html);
            } else {
                if (html.match(/^\s*$/)) {
                    $('.show-more.older').addClass('no-more');
                } else {
                    $('.timeline').append(html);
                }
            }
            var firstPage = $('.timeline li:first').data('page');
            var lastPage = $('.timeline li:last').data('page');
            if (lastPage - firstPage >= 3) {
                pageOut(!newer);
            }
            if (ActivityBrowseOptions.useShowMore) {
                updateShowMore();
            }
            restoreScrollPosition();
        }).fail(function() {
            flash('Error loading activities', 'error');
        });
    }

    function makeShowMoreHandler(newer) {
        // has to be factory to prevent closure memory leak
        // see: https://www.meteor.com/blog/2013/08/13/an-interesting-kind-of-javascript-memory-leak
        return function(event) {
            event.preventDefault();
            pageIn(newer, this.href);
        };
    }

    function makeShowMoreLink(newer, targetPage, limit) {
        var $link = $('<a class="show-more">Show more</a>');
        $link.addClass(newer ? 'newer' : 'older');
        $link.attr('href', 'pjax?page='+targetPage+'&limit='+limit);
        $link.click(makeShowMoreHandler(newer));  // has to be factory to prevent closure memory leak
        return $link;
    }

    function updateShowMore() {
        var $timeline = $('.timeline');
        if (!$timeline.length) {
            return;
        }
        var noMoreActivities = $('.show-more.older').hasClass('no-more');
        $('.page_list, .show-more').remove();
        var limit = $('.timeline').data('limit');
        var firstPage = $('.timeline li:first').data('page');
        var lastPage = $('.timeline li:last').data('page');
        if (firstPage > 0) {
            $timeline.before(makeShowMoreLink(true, firstPage-1, limit));
        }
        if (noMoreActivities) {
            $timeline.after('<div class="show-more older no-more">No more activities</div>');
        } else {
            $timeline.after(makeShowMoreLink(false, lastPage+1, limit));
        }
    }
    window.updateShowMore = updateShowMore;

    function enableInfiniteScroll() {
    }

    function enableAdvancedPaging() {
        if (ActivityBrowseOptions.useInfiniteScroll) {
            enableInfiniteScroll();
        } else if (ActivityBrowseOptions.useShowMore) {
            updateShowMore();
        }
    }

    maintainScrollState();  // http://xkcd.com/1309/
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
