function toggle_deleted( show ){
    if ( show===void(0) ) {
        show = !show_deleted;
    }
    show = !!show;

    var $rows       = $('#forge_wiki_browse tbody > tr'),
        num_deleted = $rows.filter('.deleted').toggle(show).length;

    $rows.filter(':visible').each(function(i){
        $(this).toggleClass('even', !(i%2))
    });
    if ( can_delete && num_deleted ) {
        $('#toggle_deleted span').text(show ? 'Hide' : 'Show');
        var suffix = show ? '&show_deleted=True' : '';
        $('#sort_recent').attr('href', '?sort=recent' + suffix);
        $('#sort_alpha').attr('href', '?sort=alpha' + suffix);
    }
    show_deleted = show;
    return num_deleted;
}

$(function(){
    var any_deleted = toggle_deleted(show_deleted)
    $('#toggle_deleted').click(function(){
        toggle_deleted();
        return false;
    }).toggle(!!any_deleted);
})
