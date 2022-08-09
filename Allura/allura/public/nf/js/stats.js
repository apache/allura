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

/*global jQuery, $, addCommas */
jQuery(function($) {
    // date range picker
    var input = $('#stats_date_picker input');
    if (input.length) {
        input.daterangepicker({
            onOpen: function() {
                input[0].prev_value = input.val();
            },
            onClose: function() {
                if (input[0].prev_value !== input.val()) {
                    input.parents('form').submit();
                }
            },
            rangeSplitter: 'to',
            dateFormat: 'yy-mm-dd', // yy is 4 digit
            earliestDate: new Date(input.attr('data-start-date')),
            latestDate: new Date()
        });
    }
});

function chartProjectStats(url, params, series, checkEmpty, tooltipFormat){
    var timeformat = "%y-%0m-%0d";
    tooltipFormat = tooltipFormat || function(x,y,item) {
        return y + " on " + $.plot.formatDate(new Date(parseInt(x, 10)), timeformat);
    };
    var holder = $('#stats-viz');
    var dates = $('#dates').val().split(' to ');
    var begin = Date.parse(dates[0]).setTimezoneOffset(0);
    /* Use slice(-1) to get end date, so that if there is no explicit end
     * date, end date will be the same as begin date (instead of null).
     */
    var end = Date.parse(dates.slice(-1)[0]).setTimezoneOffset(0);
    params.begin = dates[0];
    params.end = dates.slice(-1)[0];
    if (end >= begin){
      $.get(url, params, function(resp) {
        if (checkEmpty(resp.data)) {
          holder.html('<p>No results found for the parameters you have selected.</p>');
        } else {
          var number_formatter = function(val, axis) {
              if (val > 1000) {
                 return addCommas(val / 1000) + 'k';
              }
              return val;
            },
            chart = $.plot($('#project_stats_holder'), series(resp.data), {
            colors: ['#0685c6','#87c706','#c7c706','#c76606'],
            xaxis:{
              mode: "time",
              timeformat: timeformat,
              minTickSize: [1, "day"],
              min: begin,
              max: end,
              color: '#484848'},
            yaxis:{
                tickDecimals: 0,
                min: 0,
                tickFormatter: number_formatter
            },
            grid: { hoverable: true, color: '#aaa' },
            legend: {
              show: true,
              margin: 10,
              backgroundOpacity: 0.5
            }
          });
          chart.draw();
        }
      });
    }
    else{
      holder.html('<p>The date range you have chosen is not valid.</p>');
    }
  $(".busy").hide();

  var previousPoint = null;
  holder.on("plothover", function (event, pos, item) {
      if (item) {
        if (previousPoint !== item.dataIndex) {
          previousPoint = item.dataIndex;

          $(".chart-tooltip").remove();
          var x = item.datapoint[0].toFixed(0),
          y = item.datapoint[1].toFixed(0);

          $('<div class="chart-tooltip">' + tooltipFormat(x,y,item) + '</div>').css( {
            top: item.pageY - 5,
            left: item.pageX + 5,
          }).appendTo("body").fadeIn(200);
        }
      }
      else {
        $(".chart-tooltip").remove();
        previousPoint = null;
      }
  });
}
