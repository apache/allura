(function(){
    var max_page=Math.max(0, Math.floor((count+limit-1)/limit)-1);

    function requery(){
        window.location = '?q=' + encodeURIComponent(q) +
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

    $('#col_list').dialog({autoOpen: false, title:"Column Preferences"});
    $('#col_list').parent().css('border', '1px solid black');

    $('#col_menu').click(function(){
        $('#col_list').dialog('open');
    });

    $('#col_list ul').sortable({
        stop: function(){
            $('li',$(this)).each(function(i, ele){
                var $ele = $(ele);
                $ele.html($ele.html().replace(/columns-(.*?)\./g, 'columns-'+i+'.'))
            });
        }
    }).disableSelection();

})();
