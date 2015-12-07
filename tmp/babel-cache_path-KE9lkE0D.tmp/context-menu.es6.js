
'use strict';

var _createClass = (function () { function defineProperties(target, props) { for (var i = 0; i < props.length; i++) { var descriptor = props[i]; descriptor.enumerable = descriptor.enumerable || false; descriptor.configurable = true; if ('value' in descriptor) descriptor.writable = true; Object.defineProperty(target, descriptor.key, descriptor); } } return function (Constructor, protoProps, staticProps) { if (protoProps) defineProperties(Constructor.prototype, protoProps); if (staticProps) defineProperties(Constructor, staticProps); return Constructor; }; })();

function _classCallCheck(instance, Constructor) { if (!(instance instanceof Constructor)) { throw new TypeError('Cannot call a class as a function'); } }

function _inherits(subClass, superClass) { if (typeof superClass !== 'function' && superClass !== null) { throw new TypeError('Super expression must either be null or a function, not ' + typeof superClass); } subClass.prototype = Object.create(superClass && superClass.prototype, { constructor: { value: subClass, enumerable: false, writable: true, configurable: true } }); if (superClass) Object.setPrototypeOf ? Object.setPrototypeOf(subClass, superClass) : subClass.__proto__ = superClass; }

var ContextMenu = (function (_React$Component) {
    _inherits(ContextMenu, _React$Component);

    function ContextMenu(props) {
        _classCallCheck(this, ContextMenu);

        _React$Component.call(this, props);
    }

    ContextMenu.prototype.componentWillMount = function componentWillMount() {
        var _this = this;
        var mount_point;
        $('body').on('click.contextMenu', function (evt) {
            if ($(evt.target).is(':not(.contextMenu)')) {
                if ($(evt.target).is('.config-tool')) {
                    mount_point = $(evt.target).next().data('mount-point');
                } else {
                    mount_point = "";
                }
                _this.props.onOptionClick(mount_point);
            }
        });
    };

    ContextMenu.prototype.componentWillUnmount = function componentWillUnmount() {
        $("body").off('click.contextMenu');
    };

    ContextMenu.prototype.render = function render() {
        var _this = this;
        return React.createElement(
            'div',
            { className: 'contextMenu' },
            React.createElement(
                'ul',
                null,
                this.props.items.map(function (o, i) {
                    return React.createElement(
                        'li',
                        { key: i },
                        React.createElement(ToolTipLink, {
                            href: o.href,
                            classes: _this.props.classes.concat([o.className]),
                            toolTip: o.tooltip,
                            text: o.text })
                    );
                })
            )
        );
    };

    _createClass(ContextMenu, null, [{
        key: 'propTypes',
        value: {
            classes: React.PropTypes.array.isRequired,
            items: React.PropTypes.arrayOf(React.PropTypes.object).isRequired,
            onOptionClick: React.PropTypes.func.isRequired
        },
        enumerable: true
    }, {
        key: 'defaultOptions',
        value: {
            classes: []
        },
        enumerable: true
    }]);

    return ContextMenu;
})(React.Component);
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbImNvbnRleHQtbWVudS5lczYuanMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IjtBQWtCQSxZQUFZLENBQUM7Ozs7Ozs7O0lBR1AsV0FBVztjQUFYLFdBQVc7O0FBQ0YsYUFEVCxXQUFXLENBQ0QsS0FBSyxFQUFFOzhCQURqQixXQUFXOztBQUVULG9DQUFNLEtBQUssQ0FBQyxDQUFDO0tBQ2hCOztBQUhDLGVBQVcsV0FlYixrQkFBa0IsR0FBQSw4QkFBRztBQUNqQixZQUFJLEtBQUssR0FBRyxJQUFJLENBQUM7QUFDakIsWUFBSSxXQUFXLENBQUM7QUFDaEIsU0FBQyxDQUFDLE1BQU0sQ0FBQyxDQUFDLEVBQUUsQ0FBQyxtQkFBbUIsRUFBRSxVQUFVLEdBQUcsRUFBRTtBQUc3QyxnQkFBSSxDQUFDLENBQUMsR0FBRyxDQUFDLE1BQU0sQ0FBQyxDQUFDLEVBQUUsQ0FBQyxvQkFBb0IsQ0FBQyxFQUFFO0FBS3hDLG9CQUFJLENBQUMsQ0FBQyxHQUFHLENBQUMsTUFBTSxDQUFDLENBQUMsRUFBRSxDQUFDLGNBQWMsQ0FBQyxFQUFFO0FBQ2xDLCtCQUFXLEdBQUcsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxNQUFNLENBQUMsQ0FBQyxJQUFJLEVBQUUsQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLENBQUM7aUJBQzFELE1BQU07QUFFSCwrQkFBVyxHQUFHLEVBQUUsQ0FBQztpQkFDcEI7QUFDRCxxQkFBSyxDQUFDLEtBQUssQ0FBQyxhQUFhLENBQUMsV0FBVyxDQUFDLENBQUM7YUFDMUM7U0FDSixDQUFDLENBQUM7S0FDTjs7QUFuQ0MsZUFBVyxXQXFDYixvQkFBb0IsR0FBQSxnQ0FBRztBQUNuQixTQUFDLENBQUMsTUFBTSxDQUFDLENBQUMsR0FBRyxDQUFDLG1CQUFtQixDQUFDLENBQUM7S0FDdEM7O0FBdkNDLGVBQVcsV0F5Q2IsTUFBTSxHQUFBLGtCQUFHO0FBQ0wsWUFBSSxLQUFLLEdBQUcsSUFBSSxDQUFDO0FBQ2pCLGVBQ0k7O2NBQUssU0FBUyxFQUFDLGFBQWE7WUFDeEI7OztnQkFDSSxJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssQ0FBQyxHQUFHLENBQUMsVUFBVSxDQUFDLEVBQUUsQ0FBQyxFQUFFO0FBQ2pDLDJCQUFROzswQkFBSSxHQUFHLEVBQUUsQ0FBQyxBQUFDO3dCQUNmLG9CQUFDLFdBQVc7QUFDUixnQ0FBSSxFQUFFLENBQUMsQ0FBQyxJQUFJLEFBQUM7QUFDYixtQ0FBTyxFQUFFLEtBQUssQ0FBQyxLQUFLLENBQUMsT0FBTyxDQUFDLE1BQU0sQ0FBQyxDQUFDLENBQUMsQ0FBQyxTQUFTLENBQUMsQ0FBQyxBQUFDO0FBQ25ELG1DQUFPLEVBQUUsQ0FBQyxDQUFDLE9BQU8sQUFBQztBQUNuQixnQ0FBSSxFQUFFLENBQUMsQ0FBQyxJQUFJLEFBQUMsR0FBRTtxQkFDbEIsQ0FBQztpQkFDVCxDQUFDO2FBQ0Q7U0FDSCxDQUNUO0tBQ0o7O2lCQTFEQyxXQUFXOztlQUtNO0FBQ2YsbUJBQU8sRUFBRSxLQUFLLENBQUMsU0FBUyxDQUFDLEtBQUssQ0FBQyxVQUFVO0FBQ3pDLGlCQUFLLEVBQUUsS0FBSyxDQUFDLFNBQVMsQ0FBQyxPQUFPLENBQUMsS0FBSyxDQUFDLFNBQVMsQ0FBQyxNQUFNLENBQUMsQ0FBQyxVQUFVO0FBQ2pFLHlCQUFhLEVBQUUsS0FBSyxDQUFDLFNBQVMsQ0FBQyxJQUFJLENBQUMsVUFBVTtTQUNqRDs7OztlQUV1QjtBQUNwQixtQkFBTyxFQUFFLEVBQUU7U0FDZDs7OztXQWJDLFdBQVc7R0FBUyxLQUFLLENBQUMsU0FBUyIsImZpbGUiOiJjb250ZXh0LW1lbnUuZXM2LmpzIiwic291cmNlc0NvbnRlbnQiOlsiLypcbiBMaWNlbnNlZCB0byB0aGUgQXBhY2hlIFNvZnR3YXJlIEZvdW5kYXRpb24gKEFTRikgdW5kZXIgb25lXG4gb3IgbW9yZSBjb250cmlidXRvciBsaWNlbnNlIGFncmVlbWVudHMuICBTZWUgdGhlIE5PVElDRSBmaWxlXG4gZGlzdHJpYnV0ZWQgd2l0aCB0aGlzIHdvcmsgZm9yIGFkZGl0aW9uYWwgaW5mb3JtYXRpb25cbiByZWdhcmRpbmcgY29weXJpZ2h0IG93bmVyc2hpcC4gIFRoZSBBU0YgbGljZW5zZXMgdGhpcyBmaWxlXG4gdG8geW91IHVuZGVyIHRoZSBBcGFjaGUgTGljZW5zZSwgVmVyc2lvbiAyLjAgKHRoZVxuIFwiTGljZW5zZVwiKTsgeW91IG1heSBub3QgdXNlIHRoaXMgZmlsZSBleGNlcHQgaW4gY29tcGxpYW5jZVxuIHdpdGggdGhlIExpY2Vuc2UuICBZb3UgbWF5IG9idGFpbiBhIGNvcHkgb2YgdGhlIExpY2Vuc2UgYXRcblxuIGh0dHA6Ly93d3cuYXBhY2hlLm9yZy9saWNlbnNlcy9MSUNFTlNFLTIuMFxuXG4gVW5sZXNzIHJlcXVpcmVkIGJ5IGFwcGxpY2FibGUgbGF3IG9yIGFncmVlZCB0byBpbiB3cml0aW5nLFxuIHNvZnR3YXJlIGRpc3RyaWJ1dGVkIHVuZGVyIHRoZSBMaWNlbnNlIGlzIGRpc3RyaWJ1dGVkIG9uIGFuXG4gXCJBUyBJU1wiIEJBU0lTLCBXSVRIT1VUIFdBUlJBTlRJRVMgT1IgQ09ORElUSU9OUyBPRiBBTllcbiBLSU5ELCBlaXRoZXIgZXhwcmVzcyBvciBpbXBsaWVkLiAgU2VlIHRoZSBMaWNlbnNlIGZvciB0aGVcbiBzcGVjaWZpYyBsYW5ndWFnZSBnb3Zlcm5pbmcgcGVybWlzc2lvbnMgYW5kIGxpbWl0YXRpb25zXG4gdW5kZXIgdGhlIExpY2Vuc2UuXG4gKi9cbid1c2Ugc3RyaWN0JztcblxuXG5jbGFzcyBDb250ZXh0TWVudSBleHRlbmRzIFJlYWN0LkNvbXBvbmVudCB7XG4gICAgY29uc3RydWN0b3IocHJvcHMpIHtcbiAgICAgICAgc3VwZXIocHJvcHMpO1xuICAgIH1cblxuICAgIHN0YXRpYyBwcm9wVHlwZXMgPSB7XG4gICAgICAgIGNsYXNzZXM6IFJlYWN0LlByb3BUeXBlcy5hcnJheS5pc1JlcXVpcmVkLFxuICAgICAgICBpdGVtczogUmVhY3QuUHJvcFR5cGVzLmFycmF5T2YoUmVhY3QuUHJvcFR5cGVzLm9iamVjdCkuaXNSZXF1aXJlZCxcbiAgICAgICAgb25PcHRpb25DbGljazogUmVhY3QuUHJvcFR5cGVzLmZ1bmMuaXNSZXF1aXJlZFxuICAgIH07XG5cbiAgICBzdGF0aWMgZGVmYXVsdE9wdGlvbnMgPSB7XG4gICAgICAgIGNsYXNzZXM6IFtdXG4gICAgfTtcblxuICAgIGNvbXBvbmVudFdpbGxNb3VudCgpIHtcbiAgICAgICAgbGV0IF90aGlzID0gdGhpcztcbiAgICAgICAgdmFyIG1vdW50X3BvaW50O1xuICAgICAgICAkKCdib2R5Jykub24oJ2NsaWNrLmNvbnRleHRNZW51JywgZnVuY3Rpb24gKGV2dCkge1xuICAgICAgICAgICAgLyogdGhlIDpub3QgZmlsdGVyIHNob3VsZCd2ZSB3b3JrZWQgYXMgYSAybmQgcGFyYW0gdG8gLm9uKCkgaW5zdGVhZCBvZiB0aGlzLFxuICAgICAgICAgICAgIGJ1dCBjbGlja3MgaW4gdGhlIHBhZ2UgZ3V0dGVyIHdlcmUgYmVpbmcgZGVsYXllZCBmb3Igc29tZSByZWFzb24gKi9cbiAgICAgICAgICAgIGlmICgkKGV2dC50YXJnZXQpLmlzKCc6bm90KC5jb250ZXh0TWVudSknKSkge1xuXG4gICAgICAgICAgICAgICAgLyogaWYgY2xpY2tpbmcgZGlyZWN0bHkgb250byBhbm90aGVyIGdlYXIsIHNldCBpdCBkaXJlY3RseS5cbiAgICAgICAgICAgICAgICAgdGhpcyBpcyBuZWNlc3Nhcnkgc2luY2Ugc29tZXRpbWVzIG91ciBqcXVlcnkgZXZlbnRzIHNlZW0gdG8gaW50ZXJmZXJlIHdpdGggdGhlIHJlYWN0IGV2ZW50XG4gICAgICAgICAgICAgICAgIHRoYXQgaXMgc3VwcG9zZWQgdG8gaGFuZGxlIHRoaXMga2luZCBvZiB0aGluZyAqL1xuICAgICAgICAgICAgICAgIGlmICgkKGV2dC50YXJnZXQpLmlzKCcuY29uZmlnLXRvb2wnKSkge1xuICAgICAgICAgICAgICAgICAgICBtb3VudF9wb2ludCA9ICQoZXZ0LnRhcmdldCkubmV4dCgpLmRhdGEoJ21vdW50LXBvaW50Jyk7XG4gICAgICAgICAgICAgICAgfSBlbHNlIHtcbiAgICAgICAgICAgICAgICAgICAgLy8gbm8gY3VycmVudCBvcHRpb24gbWVudVxuICAgICAgICAgICAgICAgICAgICBtb3VudF9wb2ludCA9IFwiXCI7XG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgICAgIF90aGlzLnByb3BzLm9uT3B0aW9uQ2xpY2sobW91bnRfcG9pbnQpO1xuICAgICAgICAgICAgfVxuICAgICAgICB9KTtcbiAgICB9XG5cbiAgICBjb21wb25lbnRXaWxsVW5tb3VudCgpIHtcbiAgICAgICAgJChcImJvZHlcIikub2ZmKCdjbGljay5jb250ZXh0TWVudScpOyAgLy8gZGUtcmVnaXN0ZXIgb3VyIHNwZWNpZmljIGNsaWNrIGhhbmRsZXJcbiAgICB9XG5cbiAgICByZW5kZXIoKSB7XG4gICAgICAgIGxldCBfdGhpcyA9IHRoaXM7XG4gICAgICAgIHJldHVybiAoXG4gICAgICAgICAgICA8ZGl2IGNsYXNzTmFtZT1cImNvbnRleHRNZW51XCI+XG4gICAgICAgICAgICAgICAgPHVsPntcbiAgICAgICAgICAgICAgICAgICAgdGhpcy5wcm9wcy5pdGVtcy5tYXAoZnVuY3Rpb24gKG8sIGkpIHtcbiAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybiAoPGxpIGtleT17aX0+XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgPFRvb2xUaXBMaW5rXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGhyZWY9e28uaHJlZn1cbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY2xhc3Nlcz17X3RoaXMucHJvcHMuY2xhc3Nlcy5jb25jYXQoW28uY2xhc3NOYW1lXSl9XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHRvb2xUaXA9e28udG9vbHRpcH1cbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgdGV4dD17by50ZXh0fS8+XG4gICAgICAgICAgICAgICAgICAgICAgICA8L2xpPilcbiAgICAgICAgICAgICAgICAgICAgfSl9XG4gICAgICAgICAgICAgICAgPC91bD5cbiAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICApXG4gICAgfVxufVxuIl19