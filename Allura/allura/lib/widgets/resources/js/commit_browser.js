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
    var data;
    var offset = 0;
    var page_size = 12;
    var limit = 14;
    var tree, next_column, max_x_pos;

    // graph size settings
    var x_space = 10;
    var y_space = 20;
    var point_offset = 5;
    var point_size = 10;

    var $prev = $('#prev');
    var $next = $('#next');
    var $canvas = $('#commit_graph');
    var $highlighter = $('#commit_highlighter');
    var highlighter = $highlighter[0];
    var canvas = $canvas[0];
    var highlighter_ctx = highlighter.getContext('2d');
    var canvas_ctx = canvas.getContext('2d');

    // graph set up
    var height = (limit + 1) * y_space;
    var commit_rows = [];
    var taken_coords = {};
    var active_ys = [0,0]
    canvas.height=height;

    $.getJSON(document.location.href+'_data', function(data) {
        data = data;
        tree = data['built_tree'];
        next_column = data['next_column'];
        max_x_pos = x_space*next_column;

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
        drawGraph(offset);
    });
    $prev.click(function() {
        offset += page_size;
        drawGraph(offset);
        return false;
    });
    $next.click(function() {
        offset -= page_size;
        drawGraph(offset);
        return false;
    });
    $canvas.click(function(evt) {
        var y = Math.floor((evt.pageY-$canvas.offset().top) / y_space);
        var commit = commit_rows[offset+y-1];
        highlighter_ctx.clearRect(0,active_ys[0],750,active_ys[1]);
        active_ys = [commit.y_pos-y_space/4,y_space]
        highlighter_ctx.fillRect(0, active_ys[0], 750, active_ys[1]);
        $.get(commit.url+'basic',function(result){
            $('#commit_view').html(result);
        });
    });
    function drawGraph(offset) {
        // Clear the canvas and set the contetx
        var canvas_ctx = canvas.getContext('2d');
        canvas_ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas_ctx.fillStyle = "rgb(0,0,0)";
        canvas_ctx.lineWidth = 1;
        canvas_ctx.lineJoin = 'round';
        canvas_ctx.textBaseline = "top";
        canvas_ctx.font = "12px sans-serif";

        // highlighter set up
        highlighter.height=height;
        highlighter_ctx.fillStyle = "#ccc";
        // helper functions for laying out lines on the graph
        /*
        taken_coords = {};
        var detect_collision = function(x,y1,y2){
            if(taken_coords[x]){
                for(var i=0,len=taken_coords[x].length;i<len;i++){
                    if(taken_coords[x][i] >= y1 && taken_coords[x][i] <= y2){
                        return true;
                    }
                }
                return false;
            }
            else{
                return false;
            }
        };
        var adjust_x = function(x, y1, y2){
            if(detect_collision(x, y1, y2)){
                return adjust_x(x+x_space, y1, y2)
            }
            else{
                if(x > max_x_pos){
                    max_x_pos = x;
                }
                return x
            }
        }
        var take_line_coords = function(x,y1,y2){
            var taken_ys = taken_coords[x];
            if(!taken_ys){
                taken_ys = taken_coords[x] = [];
            }
            for(var i=y1;i<=y2;i=i+y_space){
                if(taken_ys.indexOf(i) == -1){
                    taken_ys.push(i);
                }
            }
        }
        // draw lines
        for(var c in tree){
            var commit = tree[c];
            var x_pos = x_space+(commit.column*x_space);
            var y_pos = y_space+((commit.row-offset)*y_space);
            for(var i=0,len=commit.parents.length;i<len;i++){
                var parent = commit.parents[i];
                canvas_ctx.beginPath();
                canvas_ctx.moveTo(x_pos+point_offset, y_pos+point_offset);
                var parent_x = x_space+tree[parent].column*x_space;
                var parent_y = y_space+((tree[parent].row)*y_space);
                var series = commit.series;
                if(tree[parent].column == commit.column){
                    canvas_ctx.lineTo(parent_x+point_offset, parent_y+point_offset);
                    take_line_coords(x_pos,y_pos,parent_y);
                }
                else if(tree[parent].column > commit.column){
                    var y1 = y_pos+point_offset*2;
                    var original_x = parent_x;
                    var adjusted_x = adjust_x(parent_x,y1,parent_y-1);
                    canvas_ctx.lineTo(adjusted_x+point_offset,y1);
                    canvas_ctx.lineTo(adjusted_x+point_offset,parent_y);
                    if(original_x != adjusted_x){
                        canvas_ctx.lineTo(adjusted_x+point_offset,parent_y);
                        canvas_ctx.lineTo(original_x+point_offset,parent_y+point_offset);
                    }
                    else{
                        canvas_ctx.lineTo(adjusted_x+point_offset,parent_y);
                    }
                    take_line_coords(adjusted_x,y_pos,parent_y);
                    series = tree[parent].series;
                }
                else{
                    var y1 = y_space+((tree[parent].row)*y_space);
                    var original_x = x_pos;
                    var adjusted_x = adjust_x(x_pos,y_pos+point_offset*3,parent_y-point_offset);
                    if(original_x != adjusted_x){
                        canvas_ctx.lineTo(adjusted_x+point_offset, y_pos+point_offset*2);
                    }
                    canvas_ctx.lineTo(adjusted_x+point_offset, y1);
                    canvas_ctx.lineTo(parent_x+point_offset, parent_y+point_offset);
                    take_line_coords(adjusted_x,y_pos,parent_y);
                    if(i > 0){
                        series = tree[parent].series;
                    }
                }
                switch(series % 6){
                case 0:
                    canvas_ctx.strokeStyle = "#a00";
                    break;
                case 1:
                    canvas_ctx.strokeStyle = "#0a0";
                    break;
                case 2:
                    canvas_ctx.strokeStyle = "#00a";
                    break;
                case 3:
                    canvas_ctx.strokeStyle = "#aa0";
                    break;
                case 4:
                    canvas_ctx.strokeStyle = "#0aa";
                    break;
                default:
                    canvas_ctx.strokeStyle = "#f0f";
                }
                canvas_ctx.stroke();
            }
        }
        */
        // draw commit points and message text
        canvas_ctx.fillStyle = "rgb(0,0,0)";
        for(var c in tree){
            var commit = tree[c];
            var x_pos = x_space+(commit.column*x_space);
            var y_pos = y_space+((commit.row-offset)*y_space);
            canvas_ctx.fillRect(x_pos, y_pos, point_size, point_size);
            canvas_ctx.fillText(commit.message, (1+next_column) * x_space, y_pos);
        }
    }
}
