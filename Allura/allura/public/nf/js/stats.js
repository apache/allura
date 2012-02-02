/*global jQuery, $, addCommas */
jQuery(function($) {
    // date range picker
    if ($('.picker input').length) {
        $('.picker input').daterangepicker({
            onOpen: function() {
                $('.picker input')[0].prev_value = $('.picker input').val();
            },
            onClose: function() {
                if ($('.picker input')[0].prev_value !== $('.picker input').val()) {
                    $('.picker input').parents('form').submit();
                    //console.log('close',$('.picker input').val());
                }
            },
            rangeSplitter: 'to',
            dateFormat: 'yy-mm-dd', // yy is 4 digit
            earliestDate: new Date($('.picker input').attr('data-start-date')),
            latestDate: new Date()
        });
    }
});

function chartProjectStats(url, params, series, checkEmpty, tooltipFormat){
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
              timeformat: "%y-%0m-%0d",
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
  holder.bind("plothover", function (event, pos, item) {
      if (item) {
        if (previousPoint !== item.dataIndex) {
          previousPoint = item.dataIndex;

          $("#tooltip").remove();
          var x = item.datapoint[0].toFixed(0),
          y = item.datapoint[1].toFixed(0);

          $('<div id="tooltip" class="tooltip">' + tooltipFormat(x,y,item) + '</div>').css( {
            position: 'absolute',
            display: 'none',
            top: item.pageY + 5,
            left: item.pageX + 5
          }).appendTo("body").fadeIn(200);
        }
      }
      else {
        $("#tooltip").remove();
        previousPoint = null;
      }
  });
}
