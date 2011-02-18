(function(){
    function requery(){
        window.location = '?q=' + q +
                          '&limit=' + limit +
                          '&page=' + page +
                          '&sort=' + encodeURIComponent(sort);
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

    $('#lightbox_col_list').append($('#col_list_form'));
    $('#col_list_form').show();

    $('#col_list_form ul').sortable({
        stop: function(){
            $('li',$(this)).each(function(i, ele){
                var $ele = $(ele);
                $ele.html($ele.html().replace(/columns-(.*?)\./g, 'columns-'+i+'.'))
            });
        }
    }).disableSelection();
})();
