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

// define indexOf for IE (code from https://developer.mozilla.org/en/JavaScript/Reference/Global_Objects/Array/indexOf)
if (!Array.prototype.indexOf)
{
  Array.prototype.indexOf = function(searchElement /*, fromIndex */)
  {
    "use strict";

    if (this === void 0 || this === null)
      throw new TypeError();

    var t = Object(this);
    var len = t.length >>> 0;
    if (len === 0)
      return -1;

    var n = 0;
    if (arguments.length > 0)
    {
      n = Number(arguments[1]);
      if (n !== n) // shortcut for verifying if it's NaN
        n = 0;
      else if (n !== 0 && n !== (1 / 0) && n !== -(1 / 0))
        n = (n > 0 || -1) * Math.floor(Math.abs(n));
    }

    if (n >= len)
      return -1;

    var k = n >= 0
          ? n
          : Math.max(len - Math.abs(n), 0);

    for (; k < len; k++)
    {
      if (k in t && t[k] === searchElement)
        return k;
    }
    return -1;
  };
}
if($('#commit_graph')){
    // graph size settings
    var x_space = 10;
    var y_space = 20;
    var point_offset = 5;
    var point_size = 10;
    var page_size = 15;

    var data = {'built_tree': {}};
    var offset = 1;
    var selected_commit = -1;
    var y_offset = offset * y_space;
    var tree, next_column = 0, max_row = 0, next_row = 0, max_visible_row;

    var $graph_holder = $('#graph_holder');
    var $scroll_placeholder = $('#graph_scroll_placeholder');
    var $canvas = $('#commit_graph');
    var $highlighter = $('#commit_highlighter');
    var highlighter = $highlighter[0];
    var canvas = $canvas[0];
    var highlighter_ctx = highlighter.getContext('2d');
    var canvas_ctx = canvas.getContext('2d');

    // graph set up
    var commit_rows = [];
    var taken_coords = {};

    highlighter_ctx.fillStyle = "#ccc";

    function setHeight(cnt) {
      /*
       * Set proper canvas height for cnt commits.
       *
       * There is a canvas height limit in all modern browsers (about 8k pixels).
       * So we keep the canvas height small and redraw the canvas on scroll with needed part of commit graph.
       * We need to keep placeholder of the needed height inside $graph_holder to enable default scrollbar.
       */
      graph_height = (cnt + .5) * y_space + 10;
      $scroll_placeholder.height(graph_height);
    }

    function drawGraph(offset) {
        // Clear the canvas
        highlighter_ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas_ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas_ctx.fillStyle = "rgb(0,0,0)";
        canvas_ctx.lineWidth = 1;
        canvas_ctx.lineJoin = 'round';
        canvas_ctx.textBaseline = "top";
        canvas_ctx.font = "12px sans-serif";

        for(var c in tree){
            var commit = tree[c];
            var x_pos = x_space+(commit.column*x_space);
            var y_pos = y_space+((commit.row-offset)*y_space);

            for(var i=0,len=commit.parents.length;i<len;i++){
                var parent = tree[commit.parents[i]];
                if (!parent) {
                    continue;
                }
                var parent_x = x_space+parent.column*x_space
                var parent_y = y_space+(parent.row-offset)*y_space;

                canvas_ctx.strokeStyle = color(Math.max(commit.column, parent.column) % 6);

                canvas_ctx.beginPath()
                canvas_ctx.moveTo(x_pos + point_offset, y_pos+point_offset);
                if (parent_x > x_pos) {
                    canvas_ctx.lineTo(parent_x + point_offset, y_pos + y_space + point_offset); // out to the right to parent column, next row
                } else {
                    canvas_ctx.lineTo(x_pos + point_offset, parent_y - y_space + point_offset); // straight down, to point one higher than parent (might not go down at all)
                }
                canvas_ctx.lineTo(parent_x+point_offset, parent_y+point_offset); // go to parent
                canvas_ctx.stroke();
            }
        }
        // draw commit points and message text
        canvas_ctx.fillStyle = "rgb(0,0,0)";
        for(var c in tree){
            var commit = tree[c];
            var x_pos = x_space+(commit.column*x_space);
            var y_pos = y_space+((commit.row-offset)*y_space);

            canvas_ctx.strokeStyle = canvas_ctx.fillStyle = color(commit.column % 6);
            canvas_ctx.beginPath();
            canvas_ctx.arc(x_pos + point_offset, y_pos + point_offset, point_offset, 0, 2 * Math.PI, false);
            canvas_ctx.fill();
            canvas_ctx.stroke();
            canvas_ctx.fillStyle = "#000";
            canvas_ctx.fillText(commit.short_id, (2+next_column) * x_space + 5, y_pos);
            canvas_ctx.fillText(commit.message, (2+next_column) * x_space + 60, y_pos);
        }
        if (data['next_commit']) {
            var y_pos = y_space+((next_row-offset)*y_space);
            canvas_ctx.fillStyle = 'rgb(0,0,256)';
            canvas_ctx.fillText(pending ? 'Loading...' : 'Show more', (2+next_column) * x_space, y_pos);
        }
    }

    var pending = false;
    function get_data(select_first) {
        if (pending) {
            return;
        }
        pending = true;
        drawGraph(offset);
        var params = {};
        if (data['next_commit']) {
            params['start'] = data['next_commit'];
        }
        $.getJSON(document.location.href+'_data', params, function(new_data) {
            $.extend(true, data, new_data);
            tree = data['built_tree'];

            // Calculate columns
            var used_columns = [];
            function take_next_free_column() {
                // default to next bigger one
                var col = used_columns.length;
                // go through each and see if any are missing, and use that
                for (var i = 0; i < used_columns.length; i++) {
                    if (used_columns.indexOf(i) === -1) {
                        col = i;
                        break;
                    }
                }
                used_columns.push(col);
                next_column = Math.max(next_column, col);
                return col;

            }
            for(var c in tree) {
                var commit = tree[c];
                if (commit.column === undefined) {
                    commit.column = take_next_free_column();
                } else {
                    // when reprocessing data after ajax load, make sure we mark what is used
                    if (used_columns.indexOf(commit.column) === -1) {
                        used_columns.push(commit.column);
                    }
                }
                if (commit.columns_now_free !== undefined) {
                    for (var i = 0; i < commit.columns_now_free.length; i++) {
                        var col_idx = used_columns.indexOf(commit.columns_now_free[i]);
                        used_columns.splice(col_idx, 1);  // splice == remove
                    }
                }
                for(var p=0; p < commit.parents.length; p++) {
                    var parent_id = commit.parents[p];
                    var parent_commit = tree[parent_id];
                    if (parent_commit) {
                        // parent may not be available (we haven't loaded all the commits yet)
                        if (!(parent_id in new_data['built_tree'])) {
                            // console.log('skipping ', parent_id, 'because it is not new, don't want to change it');
                        } else if (parent_commit.column !== undefined) {
                            // parent already has column assigned (common ancestor of 2 branches)
                            var first_col = Math.min(commit.column, parent_commit.column);
                            var second_col = Math.max(commit.column, parent_commit.column);
                            var columns_in_between = false;
                            for (var i = first_col + 1; i < second_col; i++) {
                                if (used_columns.indexOf(i) !== -1) {
                                    columns_in_between = true;
                                    break;
                                }
                            }
                            parent_commit.columns_now_free = parent_commit.columns_now_free || [];
                            if (columns_in_between) {
                                // this isn't very frequent, but if it occurs, we can't change the column like we do
                                // in the "else" portion, since that would cause lines to overlap
                                parent_commit.columns_now_free.push(commit.column);
                            } else {
                                // ok to merge into the first column
                                parent_commit.column = first_col;
                                parent_commit.columns_now_free.push(second_col);
                            }
                        } else if (p === 0) {
                            // first parent, stay in same column
                            parent_commit.column = commit.column;
                        } else {
                            // additional parents, need separate columns
                            parent_commit.column = take_next_free_column();
                        }
                    }
                }
            }

            var new_commits_row = Object.keys(new_data['built_tree']).length - 1;
            max_row = next_row + new_commits_row;
            max_visible_row = max_row + (data['next_commit'] ? 1 : 0);  // accounts for Show More link
            for (var c in new_data['built_tree']) {
                tree[c].row += next_row;
            }
            next_row = max_row + 1;
            setHeight(max_visible_row);

            // Calculate the (x,y) positions of all the commits
            for(var c in tree){
                var commit = tree[c];
                var x_pos = x_space+(commit.column*x_space);
                var y_pos = y_space+((commit.row)*y_space);
                if (!taken_coords[x_pos]){
                    taken_coords[x_pos] = [y_pos]
                }
                else if(taken_coords[x_pos].indexOf(y_pos) == -1){
                    taken_coords[x_pos].push(y_pos);
                }
                commit_rows[commit.row] = {
                    url: commit.url,
                    x_pos: x_pos,
                    y_pos: y_pos }
            }
            pending = false;
            drawGraph(offset);
            if (select_first) {
                selectCommit(0);
            }
        });
    }
    get_data(true);

    function selectCommit(index) {
      if (index < 0 || index > max_visible_row) return;
      if (data['next_commit'] && index == max_visible_row) {
          get_data();
          return;
      }
      var commit = commit_rows[index];
      highlighter_ctx.clearRect(0, 0, canvas.width, canvas.height);
      highlighter_ctx.fillRect(
          0, (commit.y_pos - y_offset) - y_space/4,
          750, y_space)
      if (selected_commit != index) {
        $('#commit_view').html('<em>Loading commit details...</em>');
        $.get(commit.url+'basic',function(result){
            $('#commit_view').html(result);
        });
      }
      selected_commit = index;
    }

    $canvas.click(function(evt) {
        var y = Math.floor((evt.pageY-$canvas.offset().top) / y_space);
        selectCommit(offset+y-1);
    });

    function color(index) {
      /* choose color for colorblind users (according to http://jfly.iam.u-tokyo.ac.jp/color/#pallet) */
      switch(index){
        case 0: return "rgb(213,94,0)";
        case 1: return "rgb(0,114,178)";
        case 2: return "rgb(240,228,66)";
        case 3: return "rgb(0,158,115)";
        case 4: return "rgb(230,159,0)";
        default: return "rgb(86,180,223)";
      }
    }

    function setOffset(x) {
      offset = Math.round(x);
      if (offset < 1)
        offset = 1;
      else if (offset > (max_visible_row - page_size))
        offset = max_visible_row - page_size + 2;
      y_offset = offset * y_space;
      drawGraph(offset);
      if (selected_commit >= offset - 1 && selected_commit <= offset + page_size)
        selectCommit(selected_commit);
    }

    $graph_holder.scroll(function() {
      var y = $(this).scrollTop();
      setOffset(y / y_space);
      $canvas.css('top', y);
      $highlighter.css('top', y);
    });
}
