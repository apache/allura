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
    function ico_active() {
    $('.ticket-filter').each(function() {
          if ($(this).find('select option').attr('selected')) {
              $(this).siblings('span').css('color', 'green');
          } else {
              $(this).siblings('span').css('color', '');
          }
    });
    }

    $( document ).ready(function() {
        ico_active();
    });

    $('table.ticket-list td a').each(function(){
      var $this = $(this);
      $this.html($this.html().replace(/\//gi,'/&#8203;'));
    });

    function requery() {
        var location = '?q=' + q +
                          '&limit=' + limit +
                          '&page=' + page +
                          '&sort=' + encodeURIComponent(sort) +
                          '&filter=' + encodeURIComponent(JSON.stringify(filter));
        // preserve displayed columns, when filter changes
        $('#col_list_form input').each(function() {
            if (this.name.indexOf('columns-') == 0) {
                var inp = $(this);
                var val = inp.val();
                if (inp.is(':checkbox') && !inp.is(':checked')) { val = ''; }
                location += '&' + this.name + '=' + encodeURIComponent(val);
            }
        });
        window.location = location;
    }

    $('.ticket-filter a[data-sort-asc]').click(function(){
        var new_sort = $(this).attr('data-sort-asc'),
        new_dir = 'asc';
        sort = new_sort + ' ' + new_dir;
        page = 0;
        requery();
    });

    $('.ticket-filter a[data-sort-desc]').click(function(){
        var new_sort = $(this).attr('data-sort-desc'),
        new_dir = 'desc';
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

    $('.ticket-list th[data-filter-toggle]').click(function() {
      var column = $(this).attr('data-filter-toggle');
      var filter_selector = '.ticket-filter[data-column="' + column + '"]';
      var filter = $(this).parents('.ticket-list').find(filter_selector);

      $('.ticket-filter').each(function() {
           if ($(this).attr('data-column') != $(this).parents('.ticket-list').find(filter_selector).attr('data-column')) {
               $(this).hide();
           }
      });
      if ($(this).find('select').length == 0) {
          $('.ticket-filter').css('height', '65px');
      } else {
          $('.ticket-filter').css('height', '370px');
      }

      var visible = filter.is(':visible');
      $(this).find('select').multiselect("close");
      filter.hide();

      if (!visible) {
        filter.show();
        $(this).find('select').multiselect("open");
      }
    });

    $('.ticket-filter select').multiselect({
        selectedText: function() {
          return 'Filtering by ' + $(this.element[0]).attr('data-label');
        }
    });
    $('.ticket-filter .close').click(function(e) {
       e.preventDefault();
       $('.ticket-filter').hide();
    });
    $('.ticket-filter .apply-filters').click(function() {
      filter = {};
      $('.ticket-filter select').each(function() {
        var val = $(this).val();
        if (val) {
          var name = this.name.replace(/^filter-/, '');
          filter[name] = val;
        }
      });
      requery();
      ico_active();
    });

    function select_active_filter() {
      for (var name in filter) {
        var fname = 'filter-' + name;
        var $select = $('select[name="' + fname + '"]');
        var $options = $select.find('option');
        $options.each(function() {
          if (filter[name].indexOf($(this).val()) != -1) {
            $(this).attr("selected", "selected");
          }
        });
        $select.multiselect('refresh');
      }
    }
    select_active_filter();
})();
