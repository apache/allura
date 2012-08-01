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
          $('#vote .votes-percent').text(data.votes_percent);
          var $vote_up = $('#vote .js-vote-up');
          var $vote_down = $('#vote .js-vote-down');
          if (vote === 'u') {
            $vote_up.toggleClass('active');
            $vote_down.removeClass('active');
          } else if (vote === 'd') {
            $vote_down.toggleClass('active');
            $vote_up.removeClass('active');
          }
        }
      }
    });
  }

  $('#vote .js-vote-up').click(function(event) {
    event.preventDefault();
    vote('u');
  });
  $('#vote .js-vote-down').click(function(event) {
    event.preventDefault();
    vote('d');
  });
});
