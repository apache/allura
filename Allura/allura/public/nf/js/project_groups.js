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
/*global privateProjectsAllowed */

$(function() {
  var cval = $.cookie('_session_id');
  // delete a group
  $('a.delete_group').click(function(evt){
    evt.preventDefault();
    var link = this;
    var csrf = $.cookie('_session_id');
    var data = {_session_id: csrf};
    if(confirm("Are you sure you want to remove the group? All users and groups in the group will lose their permissions.")){
      $.post(link.href, data, function(resp) {
        $(link).closest('tr').hide('fast');
      });
    }
  });
  // remove user from group
  var delete_user = function(evt){
    evt.preventDefault();
    var user_holder =  $(this).parent();
    if(confirm("Are you sure you want to remove the user "+user_holder.data('user')+"?")){
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
  }};
  $('#usergroup_admin a.deleter').click(delete_user);
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
        holder.html(perm_delete_ico);
        holder.find('.fa').after('&nbsp;' + escape_html(data.displayname) + ' (' + escape_html(data.username) + ')');
        holder.children('a.deleter').click(delete_user);
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
        var perm_link = perm_holder.find('a');
        var perm_icon = perm_link.find('.fa');
        if(!perm_holder.hasClass(item.has)){
          perm_holder.effect('highlight', {}, 2000);
          perm_holder.attr('class',item.has);
          perm_link.attr('title',item.text);
          if(item.has=="yes"){
            perm_icon.attr('class','fa fa-check');
            if (!privateProjectsAllowed) {
              perm_holder.hide();
            }
          }
          else if(item.has=="inherit"){
            perm_icon.attr('class','fa fa-check-circle');
            if(!privateProjectsAllowed){
              perm_holder.hide();
            }
          }
          else{
            perm_icon.attr('class','fa fa-ban');
          }
          perm_holder.find('span').remove();
          perm_link.show();
        }
        // inherited permissions may change where they're inherited from
        else if(item.has=="inherit"){
          perm_link.attr('title',item.text);
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
        perm_holder.find('span').remove();
        perm_holder.find('a').show();
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
          evt.preventDefault();
          newitem.clone().insertBefore(adder.closest('li')).find('input:text').focus();
      });
  });
  // cancel adding user
  $('#usergroup_admin').delegate(".cancel_link", "click", function(evt){
    evt.preventDefault();
    $(this).closest('li').remove();
  });
});
