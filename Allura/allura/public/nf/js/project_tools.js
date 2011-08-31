(function() {
    // Provide CSRF protection
    var cval = $.cookie('_session_id');
    var csrf_input = $('<input name="_session_id" type="hidden" value="'+cval+'">');
    // Install popup
    var install_popup = $('#lightbox_install_modal');
    var install_form = $('#install_form');
    var new_ep_name = install_form.find('input.new_ep_name');
    var new_mount_point = install_form.find('input.new_mount_point');
    var new_mount_label = install_form.find('input.new_mount_label');
    var install_tool_label = $('#install_tool_label');
    install_popup.append(install_form.show());
    $('a.install_trig').click(function () {
        var datatool = $(this).attr('data-tool');
        if (datatool) {
            var tool = defaults[datatool];
            install_tool_label.html(tool.default_label);
            new_ep_name.val(datatool);
            new_mount_point.val(tool.default_mount);
            new_mount_label.val(tool.default_label);
        } else {
            install_tool_label.html("Subproject");
            new_ep_name.val('');
            new_mount_point.val('');
            new_mount_label.val('');
        }
    });
    // Edit popup
    var $popup_title = $('#popup_title');
    var $popup_contents = $('#popup_contents');
    $('a.admin_modal').click(function () {
        var link = this;
        $popup_title.html('');
        $popup_contents.html('Loading...');
        $.get(link.href, function (data) {
            $popup_title.html($(link).html());
            $popup_contents.html(data);
            $popup_contents.find('form').append(csrf_input);
        });
    });
    // delete popup
    var form_to_delete = null;
    var mount_delete_popup = $('#lightbox_mount_delete');
    var mount_delete_form = $('#mount_delete_form');
    mount_delete_popup.append(mount_delete_form.show());
    mount_delete_form.find('.continue_delete').click(function () {
        form_to_delete.submit();
        form_to_delete = null;
    });
    mount_delete_form.find('.cancel_delete').click(function () {
        form_to_delete = null;
    });
    $('a.mount_delete').click(function () {
        form_to_delete = this.parentNode;
        return false;
    });
    // sorting
    $('#sortable').sortable({items: ".fleft"}).bind( "sortupdate", function (e) {
        var sortables = $('#sortable .fleft');
        var tools = 0;
        var subs = 0;
        var params = {'_session_id':$.cookie('_session_id')};
        for (var i = 0, len = sortables.length; i < len; i++) {
            var item = $(sortables[i]);
            var mount_point = item.find('input.mount_point');
            var shortname = item.find('input.shortname');
            if (mount_point.length) {
                params['tools-' + tools + '.mount_point'] = mount_point.val();
                params['tools-' + tools + '.ordinal'] = i;
                tools++;
            }
            if (shortname.length) {
                params['subs-' + subs + '.shortname'] = shortname.val();
                params['subs-' + subs + '.ordinal'] = i;
                subs++;
            }
        }
        $.ajax({
            type: 'POST',
            url: 'update_mount_order',
            data: params,
            success: function(xhr, textStatus, errorThrown) {
                $('#messages').notify('Tool order updated, refresh this page to see the updated project navigation.',
                                      {status: 'confirm'});
            },
            error: function(xhr, textStatus, errorThrown) {
                $('#messages').notify('Error saving tool order.',
                                      {status: 'error'});
            }
        });
    });
    // fix firefox scroll offset bug
    var userAgent = navigator.userAgent.toLowerCase();
    if(userAgent.match(/firefox/)) {
      $('#sortable').bind( "sortstart", function (event, ui) {
        ui.helper.css('margin-top', $(window).scrollTop() );
      });
      $('#sortable').bind( "sortbeforestop", function (event, ui) {
        ui.helper.css('margin-top', 0 );
      });
    }
})();