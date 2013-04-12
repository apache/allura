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

(function(){
    $('table.ticket-list td a').each(function(){
      var $this = $(this);
      $this.html($this.html().replace(/\//gi,'/&#8203;'));
    });

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
