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

/*(function($) {
    $.widget('ui.StateField', {
        _init: function() {
            console.log(this, arguments, $.Widget.prototype);
            $.Widget.prototype._init.apply(this, arguments);
        }
    });
}(jQuery));
*/
(function($) {
    var defaults  ={
        container_cls:'state-field-container',
        selector_cls:'state-field-selector',
        field_cls:'state-field',
    };

    $.fn.StateField = function(options) {
        var opts = $.extend({}, defaults, options);

        // Remove those already initialized
        var $this = $(this)
            .filter(function() {
                return $(this).data('StateField') == undefined; });

        // Initialize data
        $this.each(function() {
            $(this).data('StateField', {
                $selector:$(),
                $states:$()
            });
        });

        // Collect subwidgets into each container's data
        function __collect(name) {
            return function() {
                var $this = $(this);
                var data = $this.closest('.'+opts.container_cls).data('StateField');
                data[name] = data[name].add($this);
            }
        }
        $this
            .find('.'+opts.selector_cls).each(__collect('$selector')).end()
            .find('.'+opts.field_cls).each(__collect('$states')).end();

        // Create objects
        var $fields = $this.map(function() {
            return new StateField(this, opts) });
    }
    $.fn.StateField.defaults = defaults;

    function StateField(container, opts) {
        var self = this;
        $.extend(self, {
            container:container,
            $container:$(container),
            opts:opts,
            data:null
        });
        self.data = self.$container.data('StateField');
        /*
        console.log('Init state field with:',
                    self.data.$selector,
                    self.data.$states);
                    */
        self.data.$selector.change(function() {
            var state = $(this).val();
            //console.log('Selector', this, state);
            self.data.$states.each(function() {
                var $this = $(this);
                if($this.attr('data-name') == state) {
                    $this.show();
                } else {
                    $this.hide()
                }
            });
        }).change();
    }
    $.fn.StateField.defaults = defaults;
}(jQuery));
