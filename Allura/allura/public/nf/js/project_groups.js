$(function() {
  var cval = $.cookie('_session_id');
  // add a group
  var csrf_input = $('<input name="_session_id" type="hidden" value="'+cval+'">');
  var $popup_title = $('#popup_title');
  var $popup_contents = $('#popup_contents');
  $('a.admin_modal').click(function(evt){
    evt.preventDefault();
    evt.stopPropagation();
    var link = this;
    $popup_title.html('');
    $popup_contents.html('Loading...');
    $.get(link.href, function (data) {
      $popup_title.html(link.title);
      $popup_contents.html(data);
      $popup_contents.find('form').append(csrf_input);
      $('.btn.link.close').click(function(){
          $(this).trigger('close');
          return false;
      });
    });
  });
  // delete a group
  $('a.delete_group').click(function(evt){
    evt.preventDefault();
    var link = this;
    if(confirm("Are you sure you want to remove the group? All users and groups in the group will lose its permissions.")){
      $.get(link.href, function (data) {
        $(link).closest('tr').hide('fast');
      });
    }
  });
  // add user to group
  $('#usergroup_admin tr').delegate("form.add_user", "submit", function(evt){
    evt.preventDefault();
    var item_form = $(this);
    var params = {'role_id': item_form.closest('tr').data('group'),
                  'username': item_form.find('input').val(),
                  '_session_id': cval};
    var holder = item_form.closest('li');
    holder.html(spinner_img+' Saving...');
    $.post('add_user', params, function(data){
      if(data.error){
        flash(data.error, 'error');
        holder.slideUp('fast');
      }
      else{
        holder.attr('data-user', data.username).addClass('deleter');
        holder.html(perm_delete_ico+' '+data.displayname);
      }
    });
  });
  $('#usergroup_admin tr').delegate("form.add_user input", "blur", function(evt){
    $(this).closest('form').submit();
  });
  // remove user from group
  $('#usergroup_admin tr').delegate("li.deleter", "click", function(evt){
    var user_holder = $(evt.currentTarget);
    var params = {'role_id': user_holder.closest('tr').data('group'),
                  'username': user_holder.data('user'),
                  '_session_id': cval};
    var old_html = user_holder.html();
    user_holder.html(spinner_img+' Removing...');
    $.post('remove_user', params, function(data){
      if(data.error){
        flash(data.error, 'error');
        user_holder.html(old_html);
      }
      else{
        user_holder.slideUp('fast');
      }
    });
  });
  // add/remove permissions for a group
  var show_permission_changes = function(data){
    for(k in data){
      var group_holder = $('tr[data-group='+k+']');
      for(var i=0, len=data[k].length; i<len; ++i){
        var item = data[k][i];
        var perm_holder = group_holder.find('li[data-permission='+item.name+']');
        if(!perm_holder.hasClass(item.has)){
          perm_holder.effect('highlight', {}, 2000);
          var icon = perm_holder.find('b');
          perm_holder.attr('class',item.has).find('a').attr('title',item.text);
          if(item.has=="yes"){
            icon.attr('class','ico ico-check').attr('data-icon','3');
          }
          else if(item.has=="inherit"){
            icon.attr('class','ico ico-checkcircle').attr('data-icon','2');
          }
          else{
            icon.attr('class','ico ico-noentry').attr('data-icon','d');
          }
          perm_holder.find('span').remove();
          perm_holder.find('a').show();
        }
      }
    }
  };
  $('ul.permissions a').click(function(evt){
    evt.preventDefault();
    var perm_holder = $(this).closest('li');
    var params = {'role_id':$(this).closest('tr').data('group'),
                  'permission':perm_holder.data('permission'),
                  'allow':true,
                  '_session_id':cval};
    if(perm_holder.hasClass('yes')){
      params['allow']=false;
    }
    perm_holder.find('a').hide().after('<span>'+spinner_img+' Updating...</span>');
    $.post('change_perm', params, function(data){
      if(data.error){
        flash(data.error, 'error');
      }
      else{
        show_permission_changes(data);
      }
    });
  });
  // help text show/hide
  $show_help = $('#show_help');
  $help_text = $('#help_text');
  $('#hide_help').click(function(evt){
    evt.preventDefault();
    $help_text.slideUp('fast');
    $show_help.show();
  });
  $show_help.click(function(evt){
    evt.preventDefault();
    $help_text.slideDown('fast');
    $show_help.hide();
  });
  // show new user form when add is clicked
  $('#usergroup_admin tbody tr').each(function() {
      var newitem = $('.new-item', this);
      var adder = $('.adder', this);
      newitem.remove();
      newitem.removeClass('new-item');
      adder.click(function(evt) {
          newitem.clone().insertBefore(adder.closest('li')).find('input').focus();
      });
  });
});