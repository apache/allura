$(document).ready(function() {
  $('.js-select-project').change(function() {
    var shortname = $(this).attr('data-shortname');
    if ($(this).is(':checked')) {
      $('#selected-projects').append(' ' + shortname);
    } else {
      var shortnames = $('#selected-projects').text().split(' ');
      for (var i = 0; i < shortnames.length; i++) {
        if (shortnames[i] == shortname) break;
      }
      shortnames.splice(i, 1);
      $('#selected-projects').text(shortnames.join(' '));
    }
  });
});
