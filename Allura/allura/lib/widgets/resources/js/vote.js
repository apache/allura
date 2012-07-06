$(document).ready(function() {
  function vote(vote) {
    var $form = $('#vote form');
    var url = $form.attr('action');
    var method = $form.attr('method');
    var _session_id = $form.find('input[name="_session_id"]').val();
    $.ajax({
      url: url,
      type: method,
      data: {
        vote: vote,
        _session_id: _session_id
      },
      success: function(data) {
        if (data.status == 'ok') {
          $('#vote .votes-up').text(data.votes_up);
          $('#vote .votes-down').text(data.votes_down);
        }
      }
    });
  }

  function set_voted(vote) {
    if (vote == 'u') {
      $('#vote .votes-down').removeClass('voted');
      $('#vote .votes-up').addClass('voted');
    } else if (vote == 'd') {
      $('#vote .votes-up').removeClass('voted');
      $('#vote .votes-down').addClass('voted');
    }
  }

  $('#vote .votes-up').click(function() {
    vote('u');
    set_voted('u')
  });
  $('#vote .votes-down').click(function() {
    vote('d');
    set_voted('d');
  });
});
