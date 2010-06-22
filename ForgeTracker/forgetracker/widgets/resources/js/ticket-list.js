(function(){
var max_page=Math.max(0, Math.floor((count+limit-1)/limit)-1);

function requery(){
    window.location = '?q=' + encodeURIComponent(q) +
                      '&limit=' + limit +
                      '&page=' + page +
                      '&sort=' + encodeURIComponent(sort);
}

if ( page > 0 ){
    $('#first-page,#prev-page').removeClass('disabled');

    $('#first-page').click(function(){ page=0; requery(); });
    $('#prev-page').click(function(){ --page; requery(); });
}

if ( page < max_page ){
    $('#next-page,#last-page').removeClass('disabled');

    $('#next-page').click(function(){ ++page; requery(); });
    $('#last-page').click(function(){ page=max_page; requery(); });
}

if ( max_page <= 0 ){
    $('#first-page,#prev-page,#next-page,#last-page').remove();
}

$('th[data-sort]').click(function(){
    var old_sort = sort.split(' '),
        new_dir = {'asc':'desc', 'desc':'asc'}[old_sort[1]],
        new_sort = $(this).attr('data-sort');
    if ( new_sort !== old_sort[0] ){
        new_dir = 'asc';
    }
    sort = new_sort + ' ' + new_dir;
    page = 0;
    requery();
});
})();
