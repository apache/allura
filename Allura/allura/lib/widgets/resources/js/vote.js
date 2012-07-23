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
          if (vote === 'u') {
            $('#vote .js-vote-up').toggleClass('active');
          } else if (vote === 'd') {
            $('#vote .js-vote-down').toggleClass('active');
          }
        }
      }
    });
  }

  $('#vote .js-vote-up').click(function() {
    vote('u');
  });
  $('#vote .js-vote-down').click(function() {
    vote('d');
  });
});
