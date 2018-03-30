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
    maxPages: 3,
    maintainScrollHistory: true,
    usePjax: true,
    useHash: false, // not worth the jitter
    forceAdvancedScroll: false,
    useShowMore: false,
    useInfiniteScroll: true
}

$(function() {
    if (!$('.timeline li').length) {
        return;  // no timeline, no paging
    }

    $.expr[':']['timeline-page'] = $.expr.createPseudo(function(page) {
        // Select timeline elements by their page.  NB: only works on activity LIs.
        return function(elem) {
            return $(elem).data('page') == page;
        }
    });

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

    var scrollHandlerDelayed = null;
    function scrollHandler(event) {
        clearTimeout(scrollHandlerDelayed);
        var method = ASOptions.usePjax
            ? maintainScrollHistory_pjax
            : maintainScrollHistory_hash;
        var delay = ASOptions.usePjax
            ? 100   // scrolls replace history and don't affect scrolling, so more is ok
            : 750;  // scrolls add history and affect scrolling, so make sure they're done
        scrollHandlerDelayed = setTimeout(method, delay);
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
        // Remove newest or oldest page to keep memory usage in check.
        var $timeline = $('.timeline li');
        var firstPage = $timeline.first().data('page');
        var lastPage = $timeline.last().data('page');
        var numPages = lastPage - firstPage + 1;
        if (numPages <= ASOptions.maxPages) {
            return;
        }
        var pageToRemove = newer ? firstPage : lastPage;
        $('.timeline li:timeline-page('+pageToRemove+')').remove();
        $('.no-more.'+(newer ? 'newer' : 'older')).remove();
    }

    var pageInQueue = [];
    function pageIn(newer, url) {
        // Load a single page of either newer or older content from the URL.
        // Then calls pageOut to ensure that not too many are loaded at once,
        // to keep memory usage in check.  Also uses save/restoreScrollPosition
        // to try to keep the same content in view at the same place.
        if ($('.no-more.'+(newer ? 'newer' : 'older')).length) {
            return;
        }
        pageInQueue.push({newer: newer, url: url});
        if (pageInQueue.length > 1) {
            return;
        }
        var newerText = newer ? 'newer' : 'older';
        $.get(url, function(html) {
            var $timeline = $('.timeline');
            var empty = html.match(/^\s*$/);
            var newestPage = newer && $('.timeline li:first').data('page') <= 1;
            var limit = $('.timeline').data('limit');
            var fullPage = true;
            saveScrollPosition();
            if (!empty) {
                $timeline[newer ? 'prepend' : 'append'](html);
                var newPage = $timeline.find('li:' + (newer ? 'first' : 'last')).data('page');
                fullPage = $timeline.find('li:timeline-page('+newPage+')').length == limit;
                pageOut(!newer);
            }
            if (empty || !fullPage || newestPage) {
                makeNoMore(newer);
            }
            if (ASOptions.useShowMore) {
                // this has to be here instead of showMoreLink handler to
                // ensure that scroll changes between added / removed content
                // and Show More links combine properly and don't cause a jump
                // due to hitting the edge of the page
                updateShowMore();
            }
            restoreScrollPosition();
            pageInQueue.shift();
            if (pageInQueue.length) {
                var next = pageInQueue.shift();
                pageIn(next.newer, next.url);
            }
        }).fail(function() {
            flash('Error loading activities', 'error');
        });
    }

    function makeNoMore(newer) {
        var $timeline = $('.timeline');
        var method = newer ? 'before' : 'after';
        var cls = newer ? 'newer' : 'older';
        $timeline[method]('<div class="no-more '+cls+'">No more activities</div>');
    }

    function makePageUrl(targetPage) {
        var limit = $('.timeline').data('limit');
        return 'pjax?page='+targetPage+'&limit='+limit;
    }

    function makeShowMoreLink(newer, targetPage) {
        var cls = newer ? 'newer' : 'older';
        var url = makePageUrl(targetPage);
        var link = '<a class="show-more '+cls+'" href="'+url+'">Show More</a>';
        $('.timeline')[newer ? 'before' : 'after'](link);
        $('.show-more.'+cls).click(function(event) {
            event.preventDefault();
            pageIn(newer, this.href);
        });
    }

    function updateShowMore() {
        // Update the state of the Show More links when using "Show More"-style
        // advanced paging.
        var firstPage = $('.timeline li:first').data('page');
        var lastPage = $('.timeline li:last').data('page');
        var noMoreNewer = $('.no-more.newer').length;
        var noMoreOlder = $('.no-more.older').length;
        $('.show-more').remove();  // TODO: could update HREFs instead of always re-creating links
        if (!noMoreNewer) {
            makeShowMoreLink(true, firstPage-1);
        }
        if (!noMoreOlder) {
            makeShowMoreLink(false, lastPage+1);
        }
    }

    function enableShowMore() {
        $('.page_list').remove();
        if ($('.timeline li:first').data('page') == 0) {
            makeNoMore(true);
        }
        updateShowMore();
    }

    var currentPage = null;
    function handleInfiniteScroll(event) {
        var newPage = $('.timeline li:in-viewport:first').data('page');
        if (newPage == currentPage) {
            return;
        }
        var firstPage = $('.timeline li:first').data('page');
        var lastPage = $('.timeline li:last').data('page');
        var noMoreNewer = $('.no-more.newer').length;
        var noMoreOlder = $('.no-more.older').length;
        if (newPage < currentPage && !noMoreNewer) {
            pageIn(true, makePageUrl(firstPage-1));
        } else if (newPage > currentPage && !noMoreOlder) {
            pageIn(false, makePageUrl(lastPage+1));
        }
        currentPage = newPage;
    }

    function enableInfiniteScroll() {
        $('.page_list').remove();
        currentPage = $('.timeline li:first').data('page');
        if (currentPage == 0) {
            makeNoMore(true);
        } else {
            pageIn(true, makePageUrl(currentPage-1));
        }
        pageIn(false, makePageUrl(currentPage+1));
        $(window).scroll(handleInfiniteScroll);
    }

    function enableAdvancedPaging() {
        if (ASOptions.useInfiniteScroll) {
            enableInfiniteScroll();
        } else if (ASOptions.useShowMore) {
            enableShowMore();
        }
    }

    function enableDeleteButtons() {
        var confirmed = false;
        $('.timeline').on('mouseenter', 'li[data-can-delete]', function() {
            $(this).prepend('<input type=button value=Delete name=delete title="Permanently deletes this item from all users/projects activity records.<br>Only neighborhood admins can do this.">');
            $('input[name=delete]', this).tooltipster({contentAsHTML: true});
        });
        $('.timeline').on('mouseleave', 'li[data-can-delete]', function() {
            $('input[name=delete]', this).remove();
        });
        $('.timeline').on('click', 'li[data-can-delete] input[name=delete]', function() {
            if (!confirmed) {
                confirmed = confirm('Are you sure you want to delete this?  You cannot undo!');
                if (!confirmed) {
                    return;
                }
            }
            $(this).prop('disabled', true);
            $(this).val('Deleting...')
            var $row = $(this).closest('[data-can-delete]');
            $row.css('background', 'lightgray');
            $.post('delete_item', {
                activity_id: $row.attr('id'),
                _session_id: $.cookie('_session_id')
            }).done(function() {
                $('input[name=delete]', $row).remove();
                $row.css('text-decoration', 'line-through').removeAttr('data-can-delete');
            }).fail(function() {
                flash('Deleting failed.', 'error');
                $row.css('background', 'orange');
            });
            return false;
        });
    }

    detectFeatures();
    enableScrollHistory();
    enableAdvancedPaging();
    enableDeleteButtons();
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
