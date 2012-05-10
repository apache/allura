(function($) {

    var defaults  ={
        container_cls:'sortable-repeated-field',
        field_cls:'sortable-field',
        flist_cls:'sortable-field-list',
        stub_cls:'sortable-field-stub',
        msg_cls:'sortable-field-message',
    };

    $.fn.SortableRepeatedField = function(options) {
        var opts = $.extend({}, defaults, options);

        // Remove those already initialized
        var $this = $(this)
            .filter(function() {
                return $(this).data('SortableRepeatedField') == undefined; });

        // Initialize data
        $this.each(function() {
            $(this).data('SortableRepeatedField', {
                $flist:$(),
                $stub:$(),
                $msg:$(),
                $add_buttons:$(),
                $delete_buttons:$()})
        });

        // Collect flists, stubs, msgflds, and buttons into each container's data
        function __collect(name) {
            return function() {
                var $this = $(this);
                var data = $this.closest('.'+opts.container_cls).data('SortableRepeatedField');
                data[name] = data[name].add($this);
            }
        }
        $this
            .find('.'+opts.flist_cls).each(__collect('$flist')).end()
            .find('.'+opts.stub_cls).each(__collect('$stub')).end()
            .find('.'+opts.msg_cls).each(__collect('$msg')).end()
            .find(':button.add').each(__collect('$add_buttons')).end()
            .find(':button.delete').each(__collect('$delete_buttons')).end();

        // Create objects
        $this
            .map(function() {
                var data = $(this).data('SortableRepeatedField');
                return new SortableRepeatedField(this, opts);
            })
            .each(function() {
                this.activate() });
        return $this;
    }
    $.fn.SortableRepeatedField.defaults = defaults;

    function SortableRepeatedField(container, opts) {
        var self = this;
        $.extend(self, {
            container:container,
            $container:$(container),
            opts:opts,
            data:null,
            activate: function() {
                self.data.$add_buttons.one('click', _addField);
                self.data.$delete_buttons.one('click', _deleteField);
                self.data.$flist.sortable({stop:_renumberFields});
                self.data.$stub.hide();
                _manageMessages();
            },
            fld_name: function() {
                return self.$container.attr('data-name');
            }
        });
        self.data = self.$container.data('SortableRepeatedField');
        function _addField() {
            var tpl_name = self.fld_name() + '#';
            var $new_field = self.data.$stub
                .clone()
                .removeClass(self.opts.stub_cls)
                .addClass(self.opts.field_cls)
                .show()
                .find(':input[name^='+tpl_name+']').each(function() {
                    var $this = $(this);
                    var name = $this.attr('name');
                    if(name){
                      $this.attr('name', name.replace(
                          tpl_name,
                          self.fld_name() + '-0'));
                    }
                }).end();
            $new_field
                .find('[data-name*="' + tpl_name + '"]')
                .each(function() {
                    var $this = $(this);
                    $this.attr('data-name',
                        $this.attr('data-name')
                        .replace(tpl_name, self.fld_name() + '-0'));
                });
            $new_field.find('.hasDatepicker').removeClass('hasDatepicker');
            self.data.$flist.prepend($new_field);
            _renumberFields();
            _manageMessages();
            // Trigger event reattachment, etc.
            self.$container.removeData('SortableRepeatedField');
            $(document).trigger('clone');
        }
        function _deleteField() {
            var fld = $(this).closest('.'+self.opts.field_cls);
            fld.remove();
            _manageMessages();
        }
        function _manageMessages() {
            var attr_name = self.data.$flist.children().length > 1
                    ? 'data-nonempty-message'
                    : 'data-empty-message';
            var new_text = self.data.$msg.attr(attr_name);
            self.data.$msg.html(new_text);
        }
        function _renumberFields() {
            var prefix = self.fld_name() + '-';
            var regex = new RegExp(prefix + /\d+/.source)
            self.data.$flist.children().each(function(index) {
                $(this).find(':input[name^='+prefix+']').each(function() {
                    var $this=$(this);
                    var name=$this.attr('name');
                    var newname = name.replace(regex, prefix + index);
                    $this.attr('name', newname);
                });
                $(this).find('[data-name*="' + prefix + '"]')
                    .each(function() {
                        var $this = $(this);
                        $this.attr('data-name',
                            $this.attr('data-name')
                            .replace(regex, prefix + index));
                    });
            });
        }
    };
}(jQuery));
