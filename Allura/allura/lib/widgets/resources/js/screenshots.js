$(function() {
  $('.sortable').sortable({cursor: 'move'}).bind('sortupdate', function(e) {
    var params = {'_session_id': $.cookie('_session_id')};
    $(this).find('.screenshot').each(function(i) {
      params[$(this).data('ss-id')] = i;
    });
    $.post('sort_screenshots', params);
  });
});

