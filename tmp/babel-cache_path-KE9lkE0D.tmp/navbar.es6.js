
'use strict';

var _extends = Object.assign || function (target) { for (var i = 1; i < arguments.length; i++) { var source = arguments[i]; for (var key in source) { if (Object.prototype.hasOwnProperty.call(source, key)) { target[key] = source[key]; } } } return target; };

function _getProjectUrl() {
    var rest = arguments.length <= 0 || arguments[0] === undefined ? true : arguments[0];

    var nbhd, proj, nbhd_proj;
    var ident_classes = document.getElementById('page-body').className.split(' ');
    var _iteratorNormalCompletion = true;
    var _didIteratorError = false;
    var _iteratorError = undefined;

    try {
        for (var _iterator = ident_classes[Symbol.iterator](), _step; !(_iteratorNormalCompletion = (_step = _iterator.next()).done); _iteratorNormalCompletion = true) {
            var cls = _step.value;

            if (cls.indexOf('project-') === 0) {
                proj = cls.slice('project-'.length);
            }
        }
    } catch (err) {
        _didIteratorError = true;
        _iteratorError = err;
    } finally {
        try {
            if (!_iteratorNormalCompletion && _iterator['return']) {
                _iterator['return']();
            }
        } finally {
            if (_didIteratorError) {
                throw _iteratorError;
            }
        }
    }

    nbhd = window.location.pathname.split('/')[1];
    if (proj === '--init--') {
        nbhd_proj = nbhd;
    } else {
        nbhd_proj = nbhd + '/' + proj;
    }
    return (rest ? '/rest/' : '/') + nbhd_proj;
}

function getMountPoint(node) {
    if (node.hasOwnProperty('mount_point') && node['mount_point'] !== null) {
        return node['mount_point'];
    }
    return node.props.children[0].props.mount_point;
}

function getUrlByNode(node) {
    if (node.hasOwnProperty('url') && node['url'] !== null) {
        return node['url'];
    }
    return node.props.children[0].props.url;
}

var ToolsPropType = React.PropTypes.shape({
    mount_point: React.PropTypes.string,
    name: React.PropTypes.string.isRequired,
    url: React.PropTypes.string.isRequired,
    is_anchored: React.PropTypes.bool.isRequired,
    tool_name: React.PropTypes.string.isRequired,
    icon: React.PropTypes.string,
    children: React.PropTypes.array,
    admin_options: React.PropTypes.array
});

var NavBarItem = React.createClass({
    displayName: 'NavBarItem',

    propTypes: {
        name: React.PropTypes.string.isRequired,
        url: React.PropTypes.string.isRequired,
        currentOptionMenu: React.PropTypes.object,
        onOptionClick: React.PropTypes.func.isRequired,
        options: React.PropTypes.array
    },

    isAnchored: function isAnchored() {
        return this.props.is_anchored !== null;
    },

    render: function render() {
        var divClasses = "tb-item tb-item-edit";
        if (this.props.is_anchored) {
            divClasses += " anchored";
        }
        var spanClasses = this.props.handleType + " ordinal-item";
        if (this.props.isGrouper) {
            spanClasses += " toolbar-grouper";
        }

        return React.createElement(
            'div',
            { className: divClasses },
            React.createElement(
                'a',
                null,
                !_.isEmpty(this.props.options) && React.createElement('i', { className: 'config-tool fa fa-cog', onClick: this.handleOptionClick }),
                React.createElement(
                    'span',
                    {
                        className: spanClasses,
                        'data-mount-point': this.props.mount_point },
                    this.props.name
                )
            ),
            this.props.currentOptionMenu.tool && this.props.currentOptionMenu.tool === this.props.mount_point && React.createElement(ContextMenu, _extends({}, this.props, {
                classes: ['tool-options'],
                items: this.props.options,
                onOptionClick: this.props.onOptionClick
            }))
        );
    },

    handleOptionClick: function handleOptionClick(event) {
        this.props.onOptionClick(this.props.mount_point);
    }
});

var GroupingThreshold = React.createClass({
    displayName: 'GroupingThreshold',

    propTypes: {
        initialValue: React.PropTypes.number.isRequired
    },
    getInitialState: function getInitialState() {
        return {
            value: this.props.initialValue
        };
    },

    handleChange: function handleChange(event) {
        this.setState({
            value: event.target.value
        });
        this.props.onUpdateThreshold(event);
    },

    render: function render() {
        return React.createElement(
            'div',
            null,
            !!this.props.isHidden && React.createElement(
                'div',
                { id: 'threshold-config' },
                React.createElement(
                    'span',
                    null,
                    React.createElement(
                        'label',
                        { htmlFor: 'threshold-input' },
                        'Grouping Threshold'
                    ),
                    React.createElement('input', { type: 'number', name: 'threshold-input', className: 'tooltip',
                        title: 'Number of tools allowed before grouping.',
                        value: this.state.value,
                        onChange: this.handleChange,
                        min: '1', max: '10' })
                )
            )
        );
    }
});

var NormalNavItem = React.createClass({
    displayName: 'NormalNavItem',

    mixins: [React.addons.PureRenderMixin],

    render: function render() {

        return React.createElement(
            'li',
            { key: 'tb-norm-' + _.uniqueId() },
            React.createElement(
                'a',
                { href: this.props.url, className: this.props.classes },
                this.props.name
            ),
            this.props.children
        );
    }
});

var ToggleAddNewTool = React.createClass({
    displayName: 'ToggleAddNewTool',

    getInitialState: function getInitialState() {
        return {
            visible: false
        };
    },
    handleToggle: function handleToggle() {
        this.setState({
            visible: !this.state.visible
        });
    },
    handleOptionClick: function handleOptionClick(event) {
        console.log('event', event);
    },

    render: function render() {
        return React.createElement(
            'div',
            null,
            React.createElement(
                'a',
                { onClick: this.handleToggle, className: 'add-tool-toggle' },
                'Add New...'
            ),
            this.state.visible && React.createElement(ContextMenu, _extends({}, this.props, {
                classes: ['admin_modal'],
                onOptionClick: this.handleOptionClick,
                items: this.props.installableTools }))
        );
    }
});

var NormalNavBar = React.createClass({
    displayName: 'NormalNavBar',

    buildMenu: function buildMenu(item, i) {
        var classes = window.location.pathname.startsWith(item.url) ? 'active-nav-link' : '';

        var subMenu;
        if (item.children) {
            subMenu = item.children.map(this.buildMenu);
        }
        return React.createElement(
            NormalNavItem,
            { url: item.url, name: item.name, classes: classes, key: 'normal-nav-' + _.uniqueId() },
            React.createElement(
                'ul',
                null,
                subMenu
            )
        );
    },

    onOptionClick: function onOptionClick(e) {
        console.log(e);
    },
    render: function render() {
        var listItems = this.props.items.map(this.buildMenu);

        var mount_points = [];
        var _iteratorNormalCompletion2 = true;
        var _didIteratorError2 = false;
        var _iteratorError2 = undefined;

        try {
            for (var _iterator2 = this.props.items[Symbol.iterator](), _step2; !(_iteratorNormalCompletion2 = (_step2 = _iterator2.next()).done); _iteratorNormalCompletion2 = true) {
                var item = _step2.value;

                if (item.hasOwnProperty('mount_point') && item.mount_point !== null) {
                    mount_points.push(item.mount_point);
                } else if (item.hasOwnProperty('children')) {
                    var _iteratorNormalCompletion3 = true;
                    var _didIteratorError3 = false;
                    var _iteratorError3 = undefined;

                    try {
                        for (var _iterator3 = item.children[Symbol.iterator](), _step3; !(_iteratorNormalCompletion3 = (_step3 = _iterator3.next()).done); _iteratorNormalCompletion3 = true) {
                            var child = _step3.value;

                            mount_points.push(child.mount_point);
                        }
                    } catch (err) {
                        _didIteratorError3 = true;
                        _iteratorError3 = err;
                    } finally {
                        try {
                            if (!_iteratorNormalCompletion3 && _iterator3['return']) {
                                _iterator3['return']();
                            }
                        } finally {
                            if (_didIteratorError3) {
                                throw _iteratorError3;
                            }
                        }
                    }
                }
            }
        } catch (err) {
            _didIteratorError2 = true;
            _iteratorError2 = err;
        } finally {
            try {
                if (!_iteratorNormalCompletion2 && _iterator2['return']) {
                    _iterator2['return']();
                }
            } finally {
                if (_didIteratorError2) {
                    throw _iteratorError2;
                }
            }
        }

        console.log("mount_points", mount_points);
        return React.createElement(
            'ul',
            {
                id: 'normal-nav-bar',
                className: 'dropdown' },
            listItems,
            React.createElement(
                'li',
                { id: 'add-tool-container' },
                React.createElement(ToggleAddNewTool, _extends({}, this.props, {
                    items: this.props.installableTools,
                    onOptionClick: this.onOptionClick }))
            )
        );
    }
});

var AdminNav = React.createClass({
    displayName: 'AdminNav',

    propTypes: {
        tools: React.PropTypes.arrayOf(ToolsPropType),
        currentOptionMenu: React.PropTypes.object,
        onOptionClick: React.PropTypes.func.isRequired
    },

    buildMenu: function buildMenu(items) {
        var isSubMenu = arguments.length <= 1 || arguments[1] === undefined ? false : arguments[1];

        var _this = this;
        var tools = [];
        var anchored_tools = [];
        var end_tools = [];

        var subMenu, childOptionsOpen;

        var _iteratorNormalCompletion4 = true;
        var _didIteratorError4 = false;
        var _iteratorError4 = undefined;

        try {
            for (var _iterator4 = items[Symbol.iterator](), _step4; !(_iteratorNormalCompletion4 = (_step4 = _iterator4.next()).done); _iteratorNormalCompletion4 = true) {
                var item = _step4.value;

                if (item.children) {
                    subMenu = this.buildMenu(item.children, true);
                } else {
                    subMenu = null;
                }

                var _handle = isSubMenu ? "draggable-handle-sub" : 'draggable-handle';

                var tool_list, is_anchored;
                if (item.mount_point === 'admin') {
                    tool_list = end_tools;
                    is_anchored = true;
                } else if (item.is_anchored) {
                    tool_list = anchored_tools;
                    is_anchored = true;
                } else {
                    tool_list = tools;
                    is_anchored = false;
                }
                var core_item = React.createElement(NavBarItem, _extends({}, _this.props, {
                    mount_point: item.mount_point,
                    name: item.name,
                    handleType: _handle,
                    isGrouper: item.children && item.children.length > 0,
                    url: item.url,
                    key: 'tb-item-' + _.uniqueId(),
                    is_anchored: is_anchored,
                    options: item.admin_options
                }));
                if (subMenu) {
                    childOptionsOpen = _.contains(_.pluck(item.children, 'mount_point'), this.props.currentOptionMenu.tool);
                    tool_list.push(React.createElement(NavBarItemWithSubMenu, { key: _.uniqueId(), tool: core_item, subMenu: subMenu, childOptionsOpen: childOptionsOpen }));
                } else {
                    tool_list.push(core_item);
                }
            }
        } catch (err) {
            _didIteratorError4 = true;
            _iteratorError4 = err;
        } finally {
            try {
                if (!_iteratorNormalCompletion4 && _iterator4['return']) {
                    _iterator4['return']();
                }
            } finally {
                if (_didIteratorError4) {
                    throw _iteratorError4;
                }
            }
        }

        return React.createElement(
            'div',
            { className: 'react-drag' },
            anchored_tools,
            React.createElement(
                ReactReorderable,
                {
                    key: 'reorder-' + _.uniqueId(),
                    handle: "." + _handle,
                    mode: isSubMenu ? 'list' : 'grid',
                    onDragStart: _this.props.onToolDragStart,
                    onDrop: _this.props.onToolReorder },
                tools
            ),
            end_tools
        );
    },

    render: function render() {
        var tools = this.buildMenu(this.props.tools);
        return React.createElement(
            'div',
            null,
            tools
        );
    }
});

var NavBarItemWithSubMenu = React.createClass({
    displayName: 'NavBarItemWithSubMenu',

    render: function render() {
        return React.createElement(
            'div',
            { className: "tb-item-container" + (this.props.childOptionsOpen ? " child-options-open" : "") },
            this.props.tool,
            this.props.subMenu && React.createElement(
                AdminItemGroup,
                { key: _.uniqueId() },
                this.props.subMenu
            )
        );
    }
});

var AdminItemGroup = React.createClass({
    displayName: 'AdminItemGroup',

    render: function render() {
        return React.createElement(
            'div',
            { className: 'tb-item-grouper' },
            this.props.children
        );
    }
});

var ToggleAdminButton = React.createClass({
    displayName: 'ToggleAdminButton',

    propTypes: {
        visible: React.PropTypes.bool
    },
    render: function render() {
        var classes = this.props.visible ? 'fa fa-unlock' : 'fa fa-lock';
        return React.createElement(
            'button',
            { id: 'toggle-admin-btn', onClick: this.props.handleButtonPush, className: 'admin-toolbar-right' },
            React.createElement('i', { className: classes })
        );
    }
});

var Main = React.createClass({
    displayName: 'Main',

    propTypes: {
        initialData: React.PropTypes.shape({
            menu: React.PropTypes.arrayOf(ToolsPropType),
            installableTools: React.PropTypes.array,
            grouping_threshold: React.PropTypes.number.isRequired
        }),
        installableTools: React.PropTypes.array
    },
    getInitialState: function getInitialState() {
        return {
            data: this.props.initialData,
            visible: true,
            _session_id: $.cookie('_session_id'),
            currentOptionMenu: {
                tool: null
            }
        };
    },

    getNavJson: function getNavJson() {
        $.get(_getProjectUrl(false) + '/_nav.json?admin_options=1', (function (result) {
            if (this.isMounted()) {
                this.setState({
                    data: result
                });
            }
        }).bind(this));
    },

    handleToggleAdmin: function handleToggleAdmin() {
        this.setState({
            visible: !this.state.visible
        });
    },

    handleShowOptionMenu: function handleShowOptionMenu(mount_point) {
        this.setState({
            currentOptionMenu: {
                tool: mount_point
            }
        });
    },

    onUpdateThreshold: function onUpdateThreshold(event) {
        var _this = this;
        var thres = event.target.value;
        var url = _getProjectUrl() + '/admin/configure_tool_grouping';
        var csrf = $.cookie('_session_id');
        var data = {
            _session_id: csrf,
            grouping_threshold: thres
        };
        var _data = this.state.data;
        _data.grouping_threshold = thres;
        this.setState({
            data: _data
        });
        this.setState({
            in_progress: true
        });
        $.post(url, data, (function () {}).bind(this)).always(function () {
            _this.setState({
                in_progress: false
            });
        });

        _this.getNavJson();
        return false;
    },

    onToolReorder: function onToolReorder() {
        $('.react-drag.dragging').removeClass('dragging');

        var params = { _session_id: $.cookie('_session_id') };
        var toolNodes = $(ReactDOM.findDOMNode(this)).find('span.ordinal-item').not(".toolbar-grouper");
        for (var i = 0; i < toolNodes.length; i++) {
            params[i] = toolNodes[i].dataset.mountPoint;
        }

        var _this = this;
        var url = _getProjectUrl() + '/admin/mount_order';
        $.ajax({
            type: 'POST',
            url: url,
            data: params,
            success: function success() {
                $('#messages').notify('Tool order updated', {
                    status: 'confirm',
                    interval: 500,
                    timer: 2000
                });
                _this.getNavJson();
            },

            error: function error() {
                $('#messages').notify('Error saving tool order.', {
                    status: 'error'
                });
            }
        });
    },

    onToolDragStart: function onToolDragStart(obj) {
        var dragging_mount_point = obj.props.children.props.mount_point;
        $('[data-mount-point=' + dragging_mount_point + ']').closest('.react-drag').addClass('dragging');
    },

    render: function render() {
        var _this2 = this;

        var _this = this;
        var navBarSwitch = function navBarSwitch(showAdmin) {
            if (showAdmin) {
                return React.createElement(AdminNav, {
                    tools: _this.state.data.menu,
                    installableTools: _this.state.data.installable_tools,
                    data: _this.state.data,
                    onToolReorder: _this.onToolReorder,
                    onToolDragStart: _this.onToolDragStart,
                    editMode: _this.state.visible,
                    currentOptionMenu: _this.state.currentOptionMenu,
                    onOptionClick: _this.handleShowOptionMenu,
                    currentToolOptions: _this2.state.currentToolOptions
                });
            } else {
                return React.createElement(
                    'div',
                    null,
                    React.createElement(NormalNavBar, {
                        items: _this.state.data.menu,
                        installableTools: _this.state.data.installable_tools
                    })
                );
            }
        };
        var navBar = navBarSwitch(this.state.visible);

        var max_tool_count = _.chain(this.state.data.menu).map(function (item) {
            return item.children ? _.pluck(item.children, 'tool_name') : item.tool_name;
        }).flatten().countBy().values().max().value();
        var show_grouping_threshold = max_tool_count > 1;

        return React.createElement(
            'div',
            {
                className: 'nav_admin ' },
            navBar,
            React.createElement(
                'div',
                { id: 'bar-config' },
                show_grouping_threshold && React.createElement(GroupingThreshold, {
                    onUpdateThreshold: this.onUpdateThreshold,
                    isHidden: this.state.visible,
                    initialValue: parseInt(this.state.data.grouping_threshold) })
            ),
            React.createElement(ToggleAdminButton, {
                handleButtonPush: this.handleToggleAdmin,
                visible: this.state.visible })
        );
    }
});
//# sourceMappingURL=data:application/json;base64,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QztZQUN2QixNQUFNO1lBQ1I7O2tCQUFLLEVBQUUsRUFBQyxZQUFZO2dCQUNmLHVCQUF1QixJQUN4QixvQkFBQyxpQkFBaUI7QUFDZCxxQ0FBaUIsRUFBRyxJQUFJLENBQUMsaUJBQWlCLEFBQUU7QUFDNUMsNEJBQVEsRUFBRyxJQUFJLENBQUMsS0FBSyxDQUFDLE9BQU8sQUFBRTtBQUMvQixnQ0FBWSxFQUFHLFFBQVEsQ0FBQyxJQUFJLENBQUMsS0FBSyxDQUFDLElBQUksQ0FBQyxrQkFBa0IsQ0FBQyxBQUFFLEdBQUU7YUFDakU7WUFDTixvQkFBQyxpQkFBaUI7QUFDZCxnQ0FBZ0IsRUFBRyxJQUFJLENBQUMsaUJBQWlCLEFBQUU7QUFDM0MsdUJBQU8sRUFBRyxJQUFJLENBQUMsS0FBSyxDQUFDLE9BQU8sQUFBRSxHQUFFO1NBQ2xDLENBQ1I7S0FDTDtDQUNKLENBQUMsQ0FBQyIsImZpbGUiOiJuYXZiYXIuZXM2LmpzIiwic291cmNlc0NvbnRlbnQiOlsiLypcbiAgICAgICBMaWNlbnNlZCB0byB0aGUgQXBhY2hlIFNvZnR3YXJlIEZvdW5kYXRpb24gKEFTRikgdW5kZXIgb25lXG4gICAgICAgb3IgbW9yZSBjb250cmlidXRvciBsaWNlbnNlIGFncmVlbWVudHMuICBTZWUgdGhlIE5PVElDRSBmaWxlXG4gICAgICAgZGlzdHJpYnV0ZWQgd2l0aCB0aGlzIHdvcmsgZm9yIGFkZGl0aW9uYWwgaW5mb3JtYXRpb25cbiAgICAgICByZWdhcmRpbmcgY29weXJpZ2h0IG93bmVyc2hpcC4gIFRoZSBBU0YgbGljZW5zZXMgdGhpcyBmaWxlXG4gICAgICAgdG8geW91IHVuZGVyIHRoZSBBcGFjaGUgTGljZW5zZSwgVmVyc2lvbiAyLjAgKHRoZVxuICAgICAgIFwiTGljZW5zZVwiKTsgeW91IG1heSBub3QgdXNlIHRoaXMgZmlsZSBleGNlcHQgaW4gY29tcGxpYW5jZVxuICAgICAgIHdpdGggdGhlIExpY2Vuc2UuICBZb3UgbWF5IG9idGFpbiBhIGNvcHkgb2YgdGhlIExpY2Vuc2UgYXRcblxuICAgICAgICAgaHR0cDovL3d3dy5hcGFjaGUub3JnL2xpY2Vuc2VzL0xJQ0VOU0UtMi4wXG5cbiAgICAgICBVbmxlc3MgcmVxdWlyZWQgYnkgYXBwbGljYWJsZSBsYXcgb3IgYWdyZWVkIHRvIGluIHdyaXRpbmcsXG4gICAgICAgc29mdHdhcmUgZGlzdHJpYnV0ZWQgdW5kZXIgdGhlIExpY2Vuc2UgaXMgZGlzdHJpYnV0ZWQgb24gYW5cbiAgICAgICBcIkFTIElTXCIgQkFTSVMsIFdJVEhPVVQgV0FSUkFOVElFUyBPUiBDT05ESVRJT05TIE9GIEFOWVxuICAgICAgIEtJTkQsIGVpdGhlciBleHByZXNzIG9yIGltcGxpZWQuICBTZWUgdGhlIExpY2Vuc2UgZm9yIHRoZVxuICAgICAgIHNwZWNpZmljIGxhbmd1YWdlIGdvdmVybmluZyBwZXJtaXNzaW9ucyBhbmQgbGltaXRhdGlvbnNcbiAgICAgICB1bmRlciB0aGUgTGljZW5zZS5cbiovXG4ndXNlIHN0cmljdCc7XG5cbi8qKlxuICogR2V0cyB0aGUgY3VycmVudCBwcm9qZWN0IHVybC5cblxuICogQGNvbnN0cnVjdG9yXG4gKiBAcGFyYW0ge2Jvb2x9IHJlc3QgLSBSZXR1cm4gYSBcInJlc3RcIiB2ZXJzaW9uIG9mIHRoZSB1cmwuXG4gKiBAcmV0dXJucyB7c3RyaW5nfVxuICovXG5mdW5jdGlvbiBfZ2V0UHJvamVjdFVybChyZXN0ID0gdHJ1ZSkge1xuICAgIHZhciBuYmhkLCBwcm9qLCBuYmhkX3Byb2o7XG4gICAgdmFyIGlkZW50X2NsYXNzZXMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFnZS1ib2R5JykuY2xhc3NOYW1lLnNwbGl0KCcgJyk7XG4gICAgZm9yICh2YXIgY2xzIG9mIGlkZW50X2NsYXNzZXMpIHtcbiAgICAgICAgaWYgKGNscy5pbmRleE9mKCdwcm9qZWN0LScpID09PSAwKSB7XG4gICAgICAgICAgICBwcm9qID0gY2xzLnNsaWNlKCdwcm9qZWN0LScubGVuZ3RoKTtcbiAgICAgICAgfVxuICAgIH1cbiAgICBuYmhkID0gd2luZG93LmxvY2F0aW9uLnBhdGhuYW1lLnNwbGl0KCcvJylbMV07XG4gICAgaWYgKHByb2ogPT09ICctLWluaXQtLScpIHtcbiAgICAgICAgbmJoZF9wcm9qID0gbmJoZDtcbiAgICB9IGVsc2Uge1xuICAgICAgICBuYmhkX3Byb2ogPSBgJHtuYmhkfS8ke3Byb2p9YDtcbiAgICB9XG4gICAgcmV0dXJuIChyZXN0ID8gJy9yZXN0LycgOiAnLycpICsgbmJoZF9wcm9qO1xufVxuXG4vKipcbiAqIEdldCBhIG1vdW50IHBvaW50IGZyb20gYSBOYXZCYXJJdGVtIG5vZGUuXG5cbiAqIEBjb25zdHJ1Y3RvclxuICogQHBhcmFtIHtOYXZCYXJJdGVtfSBub2RlXG4gKiBAcmV0dXJucyB7c3RyaW5nfVxuICovXG5mdW5jdGlvbiBnZXRNb3VudFBvaW50KG5vZGUpIHtcbiAgICBpZihub2RlLmhhc093blByb3BlcnR5KCdtb3VudF9wb2ludCcpICYmIG5vZGVbJ21vdW50X3BvaW50J10gIT09IG51bGwpe1xuICAgICAgICByZXR1cm4gbm9kZVsnbW91bnRfcG9pbnQnXTtcbiAgICB9XG4gICAgcmV0dXJuIG5vZGUucHJvcHMuY2hpbGRyZW5bMF0ucHJvcHMubW91bnRfcG9pbnQ7XG59XG5cbi8qKlxuICogR2V0IGEgdXJsIGZyb20gYSBOYXZCYXJJdGVtIG5vZGUuXG5cbiAqIEBjb25zdHJ1Y3RvclxuICogQHBhcmFtIHtOYXZCYXJJdGVtfSBub2RlXG4gKiBAcmV0dXJucyB7c3RyaW5nfVxuICovXG5mdW5jdGlvbiBnZXRVcmxCeU5vZGUobm9kZSkge1xuICAgIGlmKG5vZGUuaGFzT3duUHJvcGVydHkoJ3VybCcpICYmIG5vZGVbJ3VybCddICE9PSBudWxsKXtcbiAgICAgICAgcmV0dXJuIG5vZGVbJ3VybCddO1xuICAgIH1cbiAgICByZXR1cm4gbm9kZS5wcm9wcy5jaGlsZHJlblswXS5wcm9wcy51cmw7XG59XG5cbmNvbnN0IFRvb2xzUHJvcFR5cGUgPSBSZWFjdC5Qcm9wVHlwZXMuc2hhcGUoe1xuICAgIG1vdW50X3BvaW50OiBSZWFjdC5Qcm9wVHlwZXMuc3RyaW5nLFxuICAgIG5hbWU6IFJlYWN0LlByb3BUeXBlcy5zdHJpbmcuaXNSZXF1aXJlZCxcbiAgICB1cmw6IFJlYWN0LlByb3BUeXBlcy5zdHJpbmcuaXNSZXF1aXJlZCxcbiAgICBpc19hbmNob3JlZDogUmVhY3QuUHJvcFR5cGVzLmJvb2wuaXNSZXF1aXJlZCxcbiAgICB0b29sX25hbWU6IFJlYWN0LlByb3BUeXBlcy5zdHJpbmcuaXNSZXF1aXJlZCxcbiAgICBpY29uOiBSZWFjdC5Qcm9wVHlwZXMuc3RyaW5nLFxuICAgIGNoaWxkcmVuOiBSZWFjdC5Qcm9wVHlwZXMuYXJyYXksXG4gICAgYWRtaW5fb3B0aW9uczogUmVhY3QuUHJvcFR5cGVzLmFycmF5XG59KTtcblxuLyoqXG4gKiBBIHNpbmdsZSBOYXZCYXIgaXRlbS5cblxuICogQGNvbnN0cnVjdG9yXG4gKi9cbnZhciBOYXZCYXJJdGVtID0gUmVhY3QuY3JlYXRlQ2xhc3Moe1xuICAgIHByb3BUeXBlczoge1xuICAgICAgICBuYW1lOiBSZWFjdC5Qcm9wVHlwZXMuc3RyaW5nLmlzUmVxdWlyZWQsXG4gICAgICAgIHVybDogUmVhY3QuUHJvcFR5cGVzLnN0cmluZy5pc1JlcXVpcmVkLFxuICAgICAgICBjdXJyZW50T3B0aW9uTWVudTogUmVhY3QuUHJvcFR5cGVzLm9iamVjdCxcbiAgICAgICAgb25PcHRpb25DbGljazogUmVhY3QuUHJvcFR5cGVzLmZ1bmMuaXNSZXF1aXJlZCxcbiAgICAgICAgb3B0aW9uczogUmVhY3QuUHJvcFR5cGVzLmFycmF5XG4gICAgfSxcblxuICAgIGlzQW5jaG9yZWQ6IGZ1bmN0aW9uKCkge1xuICAgICAgICByZXR1cm4gdGhpcy5wcm9wcy5pc19hbmNob3JlZCAhPT0gbnVsbDtcbiAgICB9LFxuXG4gICAgcmVuZGVyOiBmdW5jdGlvbigpIHtcbiAgICAgICAgdmFyIGRpdkNsYXNzZXMgPSBcInRiLWl0ZW0gdGItaXRlbS1lZGl0XCI7XG4gICAgICAgIGlmICh0aGlzLnByb3BzLmlzX2FuY2hvcmVkKSB7XG4gICAgICAgICAgICBkaXZDbGFzc2VzICs9IFwiIGFuY2hvcmVkXCI7XG4gICAgICAgIH1cbiAgICAgICAgdmFyIHNwYW5DbGFzc2VzID0gdGhpcy5wcm9wcy5oYW5kbGVUeXBlICsgXCIgb3JkaW5hbC1pdGVtXCI7XG4gICAgICAgIGlmICh0aGlzLnByb3BzLmlzR3JvdXBlcikge1xuICAgICAgICAgICAgc3BhbkNsYXNzZXMgKz0gXCIgdG9vbGJhci1ncm91cGVyXCJcbiAgICAgICAgfVxuXG4gICAgICAgIHJldHVybiAoXG4gICAgICAgICAgICA8ZGl2IGNsYXNzTmFtZT17IGRpdkNsYXNzZXMgfT5cbiAgICAgICAgICAgICAgICA8YT5cbiAgICAgICAgICAgICAgICAgICAgeyFfLmlzRW1wdHkodGhpcy5wcm9wcy5vcHRpb25zKSAmJiA8aSBjbGFzc05hbWU9J2NvbmZpZy10b29sIGZhIGZhLWNvZycgb25DbGljaz17dGhpcy5oYW5kbGVPcHRpb25DbGlja30+PC9pPn1cbiAgICAgICAgICAgICAgICAgICAgPHNwYW5cbiAgICAgICAgICAgICAgICAgICAgICAgIGNsYXNzTmFtZT17c3BhbkNsYXNzZXN9XG4gICAgICAgICAgICAgICAgICAgICAgICBkYXRhLW1vdW50LXBvaW50PXt0aGlzLnByb3BzLm1vdW50X3BvaW50fT5cbiAgICAgICAgICAgICAgICAgICAgICAgIHt0aGlzLnByb3BzLm5hbWV9XG4gICAgICAgICAgICAgICAgICAgIDwvc3Bhbj5cbiAgICAgICAgICAgICAgICA8L2E+XG4gICAgICAgICAgICAgICAge3RoaXMucHJvcHMuY3VycmVudE9wdGlvbk1lbnUudG9vbCAmJiB0aGlzLnByb3BzLmN1cnJlbnRPcHRpb25NZW51LnRvb2wgPT09IHRoaXMucHJvcHMubW91bnRfcG9pbnQgJiZcbiAgICAgICAgICAgICAgICAgICAgPENvbnRleHRNZW51XG4gICAgICAgICAgICAgICAgICAgICAgICB7Li4udGhpcy5wcm9wc31cbiAgICAgICAgICAgICAgICAgICAgICAgIGNsYXNzZXM9e1sndG9vbC1vcHRpb25zJ119XG4gICAgICAgICAgICAgICAgICAgICAgICBpdGVtcz17dGhpcy5wcm9wcy5vcHRpb25zfVxuICAgICAgICAgICAgICAgICAgICAgICAgb25PcHRpb25DbGljaz17dGhpcy5wcm9wcy5vbk9wdGlvbkNsaWNrfVxuICAgICAgICAgICAgICAgICAgICAvPn1cbiAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICApO1xuICAgIH0sXG5cbiAgICBoYW5kbGVPcHRpb25DbGljazogZnVuY3Rpb24oZXZlbnQpIHtcbiAgICAgICAgdGhpcy5wcm9wcy5vbk9wdGlvbkNsaWNrKHRoaXMucHJvcHMubW91bnRfcG9pbnQpO1xuICAgIH1cbn0pO1xuXG4vKipcbiAqIEFuIGlucHV0IGNvbXBvbmVudCB0aGF0IHVwZGF0ZXMgdGhlIE5hdkJhcidzIGdyb3VwaW5nIHRocmVzaG9sZC5cblxuICogQGNvbnN0cnVjdG9yXG4gKi9cbnZhciBHcm91cGluZ1RocmVzaG9sZCA9IFJlYWN0LmNyZWF0ZUNsYXNzKHtcbiAgICBwcm9wVHlwZXM6IHtcbiAgICAgICAgaW5pdGlhbFZhbHVlOiBSZWFjdC5Qcm9wVHlwZXMubnVtYmVyLmlzUmVxdWlyZWRcbiAgICB9LFxuICAgIGdldEluaXRpYWxTdGF0ZTogZnVuY3Rpb24oKSB7XG4gICAgICAgIHJldHVybiB7XG4gICAgICAgICAgICB2YWx1ZTogdGhpcy5wcm9wcy5pbml0aWFsVmFsdWVcbiAgICAgICAgfTtcbiAgICB9LFxuXG4gICAgaGFuZGxlQ2hhbmdlOiBmdW5jdGlvbihldmVudCkge1xuICAgICAgICB0aGlzLnNldFN0YXRlKHtcbiAgICAgICAgICAgIHZhbHVlOiBldmVudC50YXJnZXQudmFsdWVcbiAgICAgICAgfSk7XG4gICAgICAgIHRoaXMucHJvcHMub25VcGRhdGVUaHJlc2hvbGQoZXZlbnQpO1xuICAgIH0sXG5cbiAgICByZW5kZXI6IGZ1bmN0aW9uKCkge1xuICAgICAgICByZXR1cm4gKFxuICAgICAgICAgICAgPGRpdj5cbiAgICAgICAgICAgICAgICB7ICEhdGhpcy5wcm9wcy5pc0hpZGRlbiAmJlxuICAgICAgICAgICAgICAgIDxkaXYgaWQ9J3RocmVzaG9sZC1jb25maWcnPlxuICAgICAgICAgICAgPHNwYW4+XG4gICAgICAgICAgICAgIDxsYWJlbCBodG1sRm9yPSd0aHJlc2hvbGQtaW5wdXQnPkdyb3VwaW5nIFRocmVzaG9sZDwvbGFiZWw+XG4gICAgICAgICAgICAgICAgPGlucHV0IHR5cGU9J251bWJlcicgbmFtZT0ndGhyZXNob2xkLWlucHV0JyBjbGFzc05hbWU9J3Rvb2x0aXAnXG4gICAgICAgICAgICAgICAgICAgICAgIHRpdGxlPSdOdW1iZXIgb2YgdG9vbHMgYWxsb3dlZCBiZWZvcmUgZ3JvdXBpbmcuJ1xuICAgICAgICAgICAgICAgICAgICAgICB2YWx1ZT17IHRoaXMuc3RhdGUudmFsdWUgfVxuICAgICAgICAgICAgICAgICAgICAgICBvbkNoYW5nZT17IHRoaXMuaGFuZGxlQ2hhbmdlIH1cbiAgICAgICAgICAgICAgICAgICAgICAgbWluPScxJyBtYXg9JzEwJy8+XG4gICAgICAgICAgICAgIDwvc3Bhbj5cbiAgICAgICAgICAgICAgICA8L2Rpdj4gfVxuICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICk7XG4gICAgfVxufSk7XG5cbi8qKlxuICogVGhlIE5hdkJhciB3aGVuIGluIFwiTm9ybWFsXCIgbW9kZS5cblxuICogQGNvbnN0cnVjdG9yXG4gKi9cbnZhciBOb3JtYWxOYXZJdGVtID0gUmVhY3QuY3JlYXRlQ2xhc3Moe1xuICBtaXhpbnM6IFtSZWFjdC5hZGRvbnMuUHVyZVJlbmRlck1peGluXSxcblxuICAgIHJlbmRlcjogZnVuY3Rpb24oKSB7XG5cbiAgICAgICAgcmV0dXJuIChcbiAgICAgICAgICAgIDxsaSBrZXk9e2B0Yi1ub3JtLSR7Xy51bmlxdWVJZCgpfWB9PlxuICAgICAgICAgICAgICAgIDxhIGhyZWY9eyB0aGlzLnByb3BzLnVybCB9IGNsYXNzTmFtZT17IHRoaXMucHJvcHMuY2xhc3NlcyB9PlxuICAgICAgICAgICAgICAgICAgICB7IHRoaXMucHJvcHMubmFtZSB9XG4gICAgICAgICAgICAgICAgPC9hPlxuICAgICAgICAgICAgICAgIHt0aGlzLnByb3BzLmNoaWxkcmVufVxuICAgICAgICAgICAgPC9saT5cbiAgICAgICAgKTtcbiAgICB9XG59KTtcblxuLyoqXG4gKiBUb2dnbGUgQnV0dG9uXG5cbiAqIEBjb25zdHJ1Y3RvclxuICovXG52YXIgVG9nZ2xlQWRkTmV3VG9vbCA9IFJlYWN0LmNyZWF0ZUNsYXNzKHtcbiAgICBnZXRJbml0aWFsU3RhdGU6IGZ1bmN0aW9uKCkge1xuICAgICAgICByZXR1cm4ge1xuICAgICAgICAgICAgdmlzaWJsZTogZmFsc2VcbiAgICAgICAgfTtcbiAgICB9LFxuICAgIGhhbmRsZVRvZ2dsZTogZnVuY3Rpb24oKSB7XG4gICAgICAgIHRoaXMuc2V0U3RhdGUoe1xuICAgICAgICAgICAgdmlzaWJsZTogIXRoaXMuc3RhdGUudmlzaWJsZVxuICAgICAgICB9KTtcbiAgICB9LFxuICAgICAgICBoYW5kbGVPcHRpb25DbGljazogZnVuY3Rpb24oZXZlbnQpIHtcbiAgICAgICAgICAgIGNvbnNvbGUubG9nKCdldmVudCcsIGV2ZW50KTtcbiAgICAgICAgLy90aGlzLnByb3BzLm9uT3B0aW9uQ2xpY2sodGhpcy5wcm9wcy5tb3VudF9wb2ludCk7XG4gICAgfSxcblxuICAgIHJlbmRlcjogZnVuY3Rpb24gKCkge1xuICAgICAgICByZXR1cm4gKFxuICAgICAgICAgICAgPGRpdj5cbiAgICAgICAgICAgICAgICA8YSBvbkNsaWNrPXsgdGhpcy5oYW5kbGVUb2dnbGUgfSBjbGFzc05hbWU9XCJhZGQtdG9vbC10b2dnbGVcIj5cbiAgICAgICAgICAgICAgICAgICAgQWRkIE5ldy4uLlxuICAgICAgICAgICAgICAgIDwvYT5cbiAgICAgICAgICAgICAgICB7dGhpcy5zdGF0ZS52aXNpYmxlICYmXG4gICAgICAgICAgICAgICAgPENvbnRleHRNZW51XG4gICAgICAgICAgICAgICAgICAgIHsuLi50aGlzLnByb3BzfVxuICAgICAgICAgICAgICAgICAgICBjbGFzc2VzPXtbJ2FkbWluX21vZGFsJ119XG4gICAgICAgICAgICAgICAgICAgIG9uT3B0aW9uQ2xpY2s9e3RoaXMuaGFuZGxlT3B0aW9uQ2xpY2t9XG4gICAgICAgICAgICAgICAgICAgIGl0ZW1zPXt0aGlzLnByb3BzLmluc3RhbGxhYmxlVG9vbHN9IC8+XG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgIClcbiAgICB9XG59KTtcblxuLyoqXG4gKiBUaGUgTmF2QmFyIHdoZW4gaW4gXCJOb3JtYWxcIiBtb2RlLlxuXG4gKiBAY29uc3RydWN0b3JcbiAqL1xudmFyIE5vcm1hbE5hdkJhciA9IFJlYWN0LmNyZWF0ZUNsYXNzKHtcbiAgICBidWlsZE1lbnU6IGZ1bmN0aW9uKGl0ZW0sIGkpIHtcbiAgICAgICAgbGV0IGNsYXNzZXMgPSB3aW5kb3cubG9jYXRpb24ucGF0aG5hbWUuc3RhcnRzV2l0aChpdGVtLnVybCkgPyAnYWN0aXZlLW5hdi1saW5rJyA6ICcnO1xuXG4gICAgICAgIHZhciBzdWJNZW51O1xuICAgICAgICBpZiAoaXRlbS5jaGlsZHJlbikge1xuICAgICAgICAgICAgc3ViTWVudSA9IGl0ZW0uY2hpbGRyZW4ubWFwKHRoaXMuYnVpbGRNZW51KTtcbiAgICAgICAgfVxuICAgICAgICByZXR1cm4gKFxuICAgICAgICAgICAgPE5vcm1hbE5hdkl0ZW0gdXJsPXtpdGVtLnVybH0gbmFtZT17aXRlbS5uYW1lfSBjbGFzc2VzPXtjbGFzc2VzfSBrZXk9e2Bub3JtYWwtbmF2LSR7Xy51bmlxdWVJZCgpfWB9PlxuICAgICAgICAgICAgICAgIDx1bD5cbiAgICAgICAgICAgICAgICAgICAge3N1Yk1lbnV9XG4gICAgICAgICAgICAgICAgPC91bD5cbiAgICAgICAgICAgIDwvTm9ybWFsTmF2SXRlbT5cbiAgICAgICAgKTtcbiAgICB9LFxuXG4gICAgb25PcHRpb25DbGljazogZnVuY3Rpb24oZSl7XG4gICAgICAgIGNvbnNvbGUubG9nKGUpO1xuICAgIH0sXG4gICAgcmVuZGVyOiBmdW5jdGlvbigpIHtcbiAgICAgICAgdmFyIGxpc3RJdGVtcyA9IHRoaXMucHJvcHMuaXRlbXMubWFwKHRoaXMuYnVpbGRNZW51KTtcblxuICAgICAgICB2YXIgbW91bnRfcG9pbnRzID0gW107XG4gICAgICAgIGZvcihsZXQgaXRlbSBvZiB0aGlzLnByb3BzLml0ZW1zKXtcbiAgICAgICAgICAgIGlmKGl0ZW0uaGFzT3duUHJvcGVydHkoJ21vdW50X3BvaW50JykgJiYgaXRlbS5tb3VudF9wb2ludCAhPT0gbnVsbCl7XG4gICAgICAgICAgICAgICAgbW91bnRfcG9pbnRzLnB1c2goaXRlbS5tb3VudF9wb2ludCk7XG4gICAgICAgICAgICB9IGVsc2UgaWYoaXRlbS5oYXNPd25Qcm9wZXJ0eSgnY2hpbGRyZW4nKSl7XG4gICAgICAgICAgICAgICAgZm9yKGxldCBjaGlsZCBvZiBpdGVtLmNoaWxkcmVuKXtcbiAgICAgICAgICAgICAgICAgICAgbW91bnRfcG9pbnRzLnB1c2goY2hpbGQubW91bnRfcG9pbnQpXG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfVxuICAgICAgICB9XG4gICAgICAgIGNvbnNvbGUubG9nKFwibW91bnRfcG9pbnRzXCIsIG1vdW50X3BvaW50cyk7XG4gICAgICAgIHJldHVybiAoXG4gICAgICAgICAgICA8dWxcbiAgICAgICAgICAgICAgICBpZD1cIm5vcm1hbC1uYXYtYmFyXCJcbiAgICAgICAgICAgICAgICBjbGFzc05hbWU9XCJkcm9wZG93blwiPlxuICAgICAgICAgICAgICAgIHsgbGlzdEl0ZW1zIH1cbiAgICAgICAgICAgICAgICA8bGkgaWQ9XCJhZGQtdG9vbC1jb250YWluZXJcIj5cbiAgICAgICAgICAgICAgICAgICAgPFRvZ2dsZUFkZE5ld1Rvb2xcbiAgICAgICAgICAgICAgICAgICAgICAgIHsuLi50aGlzLnByb3BzfVxuICAgICAgICAgICAgICAgICAgICAgICAgaXRlbXM9e3RoaXMucHJvcHMuaW5zdGFsbGFibGVUb29sc31cbiAgICAgICAgICAgICAgICAgICAgICAgIG9uT3B0aW9uQ2xpY2s9e3RoaXMub25PcHRpb25DbGlja30gLz5cbiAgICAgICAgICAgICAgICA8L2xpPlxuICAgICAgICAgICAgPC91bD5cbiAgICAgICAgKTtcbiAgICB9XG59KTtcblxuLyoqXG4gKiBUaGUgTmF2QmFyIHdoZW4gaW4gXCJBZG1pblwiIG1vZGUuXG4gKiBAY29uc3RydWN0b3JcbiAqL1xudmFyIEFkbWluTmF2ID0gUmVhY3QuY3JlYXRlQ2xhc3Moe1xuICAgIHByb3BUeXBlczoge1xuICAgICAgICB0b29sczogUmVhY3QuUHJvcFR5cGVzLmFycmF5T2YoVG9vbHNQcm9wVHlwZSksXG4gICAgICAgIGN1cnJlbnRPcHRpb25NZW51OiBSZWFjdC5Qcm9wVHlwZXMub2JqZWN0LFxuICAgICAgICBvbk9wdGlvbkNsaWNrOiBSZWFjdC5Qcm9wVHlwZXMuZnVuYy5pc1JlcXVpcmVkXG4gICAgfSxcblxuICAgIGJ1aWxkTWVudTogZnVuY3Rpb24gKGl0ZW1zLCBpc1N1Yk1lbnU9ZmFsc2UpIHtcbiAgICAgICAgdmFyIF90aGlzID0gdGhpcztcbiAgICAgICAgdmFyIFt0b29scywgYW5jaG9yZWRfdG9vbHMsIGVuZF90b29sc10gPSBbW10sIFtdLCBbXV07XG4gICAgICAgIHZhciBzdWJNZW51LCBjaGlsZE9wdGlvbnNPcGVuO1xuXG4gICAgICAgIGZvciAobGV0IGl0ZW0gb2YgaXRlbXMpIHtcbiAgICAgICAgICAgIGlmIChpdGVtLmNoaWxkcmVuKSB7XG4gICAgICAgICAgICAgICAgc3ViTWVudSA9IHRoaXMuYnVpbGRNZW51KGl0ZW0uY2hpbGRyZW4sIHRydWUpO1xuICAgICAgICAgICAgfSBlbHNlIHtcbiAgICAgICAgICAgICAgICBzdWJNZW51ID0gbnVsbDtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgdmFyIF9oYW5kbGUgPSBpc1N1Yk1lbnUgPyBcImRyYWdnYWJsZS1oYW5kbGUtc3ViXCIgOiAnZHJhZ2dhYmxlLWhhbmRsZSc7XG5cbiAgICAgICAgICAgIHZhciB0b29sX2xpc3QsIGlzX2FuY2hvcmVkO1xuICAgICAgICAgICAgaWYgKGl0ZW0ubW91bnRfcG9pbnQgPT09ICdhZG1pbicpIHtcbiAgICAgICAgICAgICAgICAvLyBmb3JjZSBhZG1pbiB0byBlbmQsIGp1c3QgbGlrZSAnUHJvamVjdC5zaXRlbWFwKCknIGRvZXNcbiAgICAgICAgICAgICAgICB0b29sX2xpc3QgPSBlbmRfdG9vbHM7XG4gICAgICAgICAgICAgICAgaXNfYW5jaG9yZWQgPSB0cnVlO1xuICAgICAgICAgICAgfSBlbHNlIGlmIChpdGVtLmlzX2FuY2hvcmVkKSB7XG4gICAgICAgICAgICAgICAgdG9vbF9saXN0ID0gYW5jaG9yZWRfdG9vbHM7XG4gICAgICAgICAgICAgICAgaXNfYW5jaG9yZWQgPSB0cnVlO1xuICAgICAgICAgICAgfSBlbHNlIHtcbiAgICAgICAgICAgICAgICB0b29sX2xpc3QgPSB0b29scztcbiAgICAgICAgICAgICAgICBpc19hbmNob3JlZCA9IGZhbHNlO1xuICAgICAgICAgICAgfVxuICAgICAgICAgICAgdmFyIGNvcmVfaXRlbSA9IDxOYXZCYXJJdGVtXG4gICAgICAgICAgICAgICAgey4uLl90aGlzLnByb3BzfVxuICAgICAgICAgICAgICAgIG1vdW50X3BvaW50PXsgaXRlbS5tb3VudF9wb2ludCB9XG4gICAgICAgICAgICAgICAgbmFtZT17IGl0ZW0ubmFtZSB9XG4gICAgICAgICAgICAgICAgaGFuZGxlVHlwZT17X2hhbmRsZX1cbiAgICAgICAgICAgICAgICBpc0dyb3VwZXI9e2l0ZW0uY2hpbGRyZW4gJiYgaXRlbS5jaGlsZHJlbi5sZW5ndGggPiAwfVxuICAgICAgICAgICAgICAgIHVybD17IGl0ZW0udXJsIH1cbiAgICAgICAgICAgICAgICBrZXk9eyAndGItaXRlbS0nICsgXy51bmlxdWVJZCgpIH1cbiAgICAgICAgICAgICAgICBpc19hbmNob3JlZD17IGlzX2FuY2hvcmVkIH1cbiAgICAgICAgICAgICAgICBvcHRpb25zPXsgaXRlbS5hZG1pbl9vcHRpb25zIH1cbiAgICAgICAgICAgIC8+O1xuICAgICAgICAgICAgaWYgKHN1Yk1lbnUpIHtcbiAgICAgICAgICAgICAgICBjaGlsZE9wdGlvbnNPcGVuID0gXy5jb250YWlucyhfLnBsdWNrKGl0ZW0uY2hpbGRyZW4sICdtb3VudF9wb2ludCcpLCB0aGlzLnByb3BzLmN1cnJlbnRPcHRpb25NZW51LnRvb2wpO1xuICAgICAgICAgICAgICAgIHRvb2xfbGlzdC5wdXNoKDxOYXZCYXJJdGVtV2l0aFN1Yk1lbnUga2V5PXtfLnVuaXF1ZUlkKCl9IHRvb2w9e2NvcmVfaXRlbX0gc3ViTWVudT17c3ViTWVudX0gY2hpbGRPcHRpb25zT3Blbj17Y2hpbGRPcHRpb25zT3Blbn0vPik7XG4gICAgICAgICAgICB9IGVsc2Uge1xuICAgICAgICAgICAgICAgIHRvb2xfbGlzdC5wdXNoKGNvcmVfaXRlbSk7XG4gICAgICAgICAgICB9XG4gICAgICAgIH1cblxuICAgICAgICByZXR1cm4gKFxuICAgICAgICAgICAgPGRpdiBjbGFzc05hbWU9J3JlYWN0LWRyYWcnPlxuICAgICAgICAgICAgICAgIHsgYW5jaG9yZWRfdG9vbHMgfVxuICAgICAgICAgICAgICAgIDxSZWFjdFJlb3JkZXJhYmxlXG4gICAgICAgICAgICAgICAgICAgIGtleT17ICdyZW9yZGVyLScgKyBfLnVuaXF1ZUlkKCkgfVxuICAgICAgICAgICAgICAgICAgICBoYW5kbGU9e1wiLlwiICsgX2hhbmRsZX1cbiAgICAgICAgICAgICAgICAgICAgbW9kZT17IGlzU3ViTWVudSA/ICdsaXN0JyA6ICdncmlkJyB9XG4gICAgICAgICAgICAgICAgICAgIG9uRHJhZ1N0YXJ0PXsgX3RoaXMucHJvcHMub25Ub29sRHJhZ1N0YXJ0IH1cbiAgICAgICAgICAgICAgICAgICAgb25Ecm9wPXsgX3RoaXMucHJvcHMub25Ub29sUmVvcmRlciB9PlxuICAgICAgICAgICAgICAgICAgICB7IHRvb2xzIH1cbiAgICAgICAgICAgICAgICA8L1JlYWN0UmVvcmRlcmFibGU+XG4gICAgICAgICAgICAgICAgeyBlbmRfdG9vbHMgfVxuICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICk7XG4gICAgfSxcblxuICAgIHJlbmRlcjogZnVuY3Rpb24gKCkge1xuICAgICAgICB2YXIgdG9vbHMgPSB0aGlzLmJ1aWxkTWVudSh0aGlzLnByb3BzLnRvb2xzKTtcbiAgICAgICAgcmV0dXJuIDxkaXY+e3Rvb2xzfTwvZGl2PjtcbiAgICB9XG59KTtcblxudmFyIE5hdkJhckl0ZW1XaXRoU3ViTWVudSA9IFJlYWN0LmNyZWF0ZUNsYXNzKHtcbiAgICByZW5kZXI6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgcmV0dXJuIChcbiAgICAgICAgICAgIDxkaXYgY2xhc3NOYW1lPXtcInRiLWl0ZW0tY29udGFpbmVyXCIgKyAodGhpcy5wcm9wcy5jaGlsZE9wdGlvbnNPcGVuID8gXCIgY2hpbGQtb3B0aW9ucy1vcGVuXCIgOiBcIlwiKX0+XG4gICAgICAgICAgICAgICAgeyB0aGlzLnByb3BzLnRvb2wgfVxuICAgICAgICAgICAgICAgIHt0aGlzLnByb3BzLnN1Yk1lbnUgJiZcbiAgICAgICAgICAgICAgICA8QWRtaW5JdGVtR3JvdXAga2V5PXtfLnVuaXF1ZUlkKCl9PlxuICAgICAgICAgICAgICAgICAgICB7dGhpcy5wcm9wcy5zdWJNZW51fVxuICAgICAgICAgICAgICAgIDwvQWRtaW5JdGVtR3JvdXA+XG4gICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICApO1xuICAgIH1cbn0pO1xuXG5cbi8qKlxuICogVGhlIE5hdkJhciB3aGVuIGluIFwiQWRtaW5cIiBtb2RlLlxuICogQGNvbnN0cnVjdG9yXG4gKi9cbnZhciBBZG1pbkl0ZW1Hcm91cCA9IFJlYWN0LmNyZWF0ZUNsYXNzKHtcbiAgICByZW5kZXI6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgcmV0dXJuIChcbiAgICAgICAgICAgIDxkaXYgY2xhc3NOYW1lPVwidGItaXRlbS1ncm91cGVyXCI+XG4gICAgICAgICAgICAgICAge3RoaXMucHJvcHMuY2hpbGRyZW59XG4gICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgKTtcbiAgICB9XG59KTtcblxuLyoqXG4gKiBUaGUgYnV0dG9uIHRoYXQgdG9nZ2xlcyBOYXZCYXIgbW9kZXMuXG5cbiAqIEBjb25zdHJ1Y3RvclxuICovXG52YXIgVG9nZ2xlQWRtaW5CdXR0b24gPSBSZWFjdC5jcmVhdGVDbGFzcyh7XG4gICAgcHJvcFR5cGVzOiB7XG4gICAgICAgIHZpc2libGU6IFJlYWN0LlByb3BUeXBlcy5ib29sXG4gICAgfSxcbiAgICByZW5kZXI6IGZ1bmN0aW9uKCkge1xuICAgICAgICB2YXIgY2xhc3NlcyA9IHRoaXMucHJvcHMudmlzaWJsZSA/ICdmYSBmYS11bmxvY2snIDogJ2ZhIGZhLWxvY2snO1xuICAgICAgICByZXR1cm4gKFxuICAgICAgICAgICAgPGJ1dHRvbiBpZD0ndG9nZ2xlLWFkbWluLWJ0bicgb25DbGljaz17IHRoaXMucHJvcHMuaGFuZGxlQnV0dG9uUHVzaCB9IGNsYXNzTmFtZT0nYWRtaW4tdG9vbGJhci1yaWdodCc+XG4gICAgICAgICAgICAgICAgPGkgY2xhc3NOYW1lPXsgY2xhc3NlcyB9PjwvaT5cbiAgICAgICAgICAgIDwvYnV0dG9uPlxuICAgICAgICApO1xuICAgIH1cbn0pO1xuXG4vKipcbiAqIFRoZSBtYWluIFwiY29udHJvbGxlciB2aWV3XCIgb2YgdGhlIE5hdkJhci5cblxuICogQGNvbnN0cnVjdG9yXG4gKiBAcGFyYW0ge29iamVjdH0gaW5pdGlhbERhdGFcbiAqL1xudmFyIE1haW4gPSBSZWFjdC5jcmVhdGVDbGFzcyh7XG4gICAgcHJvcFR5cGVzOiB7XG4gICAgICAgIGluaXRpYWxEYXRhOiBSZWFjdC5Qcm9wVHlwZXMuc2hhcGUoe1xuICAgICAgICAgICAgbWVudTogUmVhY3QuUHJvcFR5cGVzLmFycmF5T2YoVG9vbHNQcm9wVHlwZSksXG4gICAgICAgICAgICBpbnN0YWxsYWJsZVRvb2xzOiBSZWFjdC5Qcm9wVHlwZXMuYXJyYXksXG4gICAgICAgICAgICBncm91cGluZ190aHJlc2hvbGQ6IFJlYWN0LlByb3BUeXBlcy5udW1iZXIuaXNSZXF1aXJlZFxuICAgICAgICB9KSxcbiAgICAgICAgaW5zdGFsbGFibGVUb29sczogUmVhY3QuUHJvcFR5cGVzLmFycmF5XG4gICAgfSxcbiAgICBnZXRJbml0aWFsU3RhdGU6IGZ1bmN0aW9uKCkge1xuICAgICAgICByZXR1cm4ge1xuICAgICAgICAgICAgZGF0YTogdGhpcy5wcm9wcy5pbml0aWFsRGF0YSxcbiAgICAgICAgICAgIHZpc2libGU6IHRydWUsXG4gICAgICAgICAgICBfc2Vzc2lvbl9pZDogJC5jb29raWUoJ19zZXNzaW9uX2lkJyksXG4gICAgICAgICAgICBjdXJyZW50T3B0aW9uTWVudToge1xuICAgICAgICAgICAgICAgIHRvb2w6IG51bGxcbiAgICAgICAgICAgIH1cbiAgICAgICAgfTtcbiAgICB9LFxuXG4gICAgLyoqXG4gICAgICogV2hlbiBpbnZva2VkLCB0aGlzIHVwZGF0ZXMgdGhlIHN0YXRlIHdpdGggdGhlIGxhdGVzdCBkYXRhIGZyb20gdGhlIHNlcnZlci5cbiAgICAgKi9cbiAgICBnZXROYXZKc29uOiBmdW5jdGlvbigpIHtcbiAgICAgICAgJC5nZXQoYCR7X2dldFByb2plY3RVcmwoZmFsc2UpfS9fbmF2Lmpzb24/YWRtaW5fb3B0aW9ucz0xYCwgZnVuY3Rpb24ocmVzdWx0KSB7XG4gICAgICAgICAgICBpZiAodGhpcy5pc01vdW50ZWQoKSkge1xuICAgICAgICAgICAgICAgIHRoaXMuc2V0U3RhdGUoe1xuICAgICAgICAgICAgICAgICAgICBkYXRhOiByZXN1bHRcbiAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIH1cbiAgICAgICAgfS5iaW5kKHRoaXMpKTtcbiAgICB9LFxuICAgIC8qKlxuICAgICAqIEhhbmRsZXMgdGhlIGxvY2tpbmcgYW5kIHVubG9ja2luZyBvZiB0aGUgTmF2QmFyXG4gICAgICovXG4gICAgaGFuZGxlVG9nZ2xlQWRtaW46IGZ1bmN0aW9uKCkge1xuICAgICAgICB0aGlzLnNldFN0YXRlKHtcbiAgICAgICAgICAgIHZpc2libGU6ICF0aGlzLnN0YXRlLnZpc2libGVcbiAgICAgICAgfSk7XG4gICAgfSxcblxuICAgIGhhbmRsZVNob3dPcHRpb25NZW51OiBmdW5jdGlvbiAobW91bnRfcG9pbnQpIHtcbiAgICAgICAgdGhpcy5zZXRTdGF0ZSh7XG4gICAgICAgICAgICBjdXJyZW50T3B0aW9uTWVudToge1xuICAgICAgICAgICAgICAgIHRvb2w6IG1vdW50X3BvaW50LFxuICAgICAgICAgICAgfVxuICAgICAgICB9KTtcbiAgICB9LFxuXG4gICAgLyoqXG4gICAgICogSGFuZGxlcyB0aGUgY2hhbmdpbmcgb2YgdGhlIE5hdkJhcnMgZ3JvdXBpbmcgdGhyZXNob2xkLlxuXG4gICAgICogQHBhcmFtIHtvYmplY3R9IGV2ZW50XG4gICAgICovXG4gICAgb25VcGRhdGVUaHJlc2hvbGQ6IGZ1bmN0aW9uKGV2ZW50KSB7XG4gICAgICAgIHZhciBfdGhpcyA9IHRoaXM7XG4gICAgICAgIHZhciB0aHJlcyA9IGV2ZW50LnRhcmdldC52YWx1ZTtcbiAgICAgICAgdmFyIHVybCA9IGAke19nZXRQcm9qZWN0VXJsKCl9L2FkbWluL2NvbmZpZ3VyZV90b29sX2dyb3VwaW5nYDtcbiAgICAgICAgdmFyIGNzcmYgPSAkLmNvb2tpZSgnX3Nlc3Npb25faWQnKTtcbiAgICAgICAgdmFyIGRhdGEgPSB7XG4gICAgICAgICAgICBfc2Vzc2lvbl9pZDogY3NyZixcbiAgICAgICAgICAgIGdyb3VwaW5nX3RocmVzaG9sZDogdGhyZXNcbiAgICAgICAgfTtcbiAgICAgICAgdmFyIF9kYXRhID0gdGhpcy5zdGF0ZS5kYXRhO1xuICAgICAgICBfZGF0YS5ncm91cGluZ190aHJlc2hvbGQgPSB0aHJlcztcbiAgICAgICAgdGhpcy5zZXRTdGF0ZSh7XG4gICAgICAgICAgICBkYXRhOiBfZGF0YVxuICAgICAgICB9KTtcbiAgICAgICAgdGhpcy5zZXRTdGF0ZSh7XG4gICAgICAgICAgICBpbl9wcm9ncmVzczogdHJ1ZVxuICAgICAgICB9KTtcbiAgICAgICAgJC5wb3N0KHVybCwgZGF0YSwgZnVuY3Rpb24oKSB7XG4gICAgICAgIH0uYmluZCh0aGlzKSkuYWx3YXlzKGZ1bmN0aW9uKCkge1xuICAgICAgICAgICAgX3RoaXMuc2V0U3RhdGUoe1xuICAgICAgICAgICAgICAgIGluX3Byb2dyZXNzOiBmYWxzZVxuICAgICAgICAgICAgfSk7XG4gICAgICAgIH0pO1xuXG4gICAgICAgIF90aGlzLmdldE5hdkpzb24oKTtcbiAgICAgICAgcmV0dXJuIGZhbHNlO1xuICAgIH0sXG5cbiAgICAvKipcbiAgICAgKiBIYW5kbGVzIHRoZSBzZW5kaW5nIGFuZCB1cGRhdGluZyB0b29sIG9yZGluYWxzLlxuXG4gICAgICogQHBhcmFtIHthcnJheX0gZGF0YSAtIEFycmF5IG9mIHRvb2xzXG4gICAgICovXG4gICAgb25Ub29sUmVvcmRlcjogZnVuY3Rpb24oKSB7XG4gICAgICAgICQoJy5yZWFjdC1kcmFnLmRyYWdnaW5nJykucmVtb3ZlQ2xhc3MoJ2RyYWdnaW5nJyk7XG5cbiAgICAgICAgdmFyIHBhcmFtcyA9IHtfc2Vzc2lvbl9pZDogJC5jb29raWUoJ19zZXNzaW9uX2lkJyl9O1xuICAgICAgICB2YXIgdG9vbE5vZGVzID0gJChSZWFjdERPTS5maW5kRE9NTm9kZSh0aGlzKSkuZmluZCgnc3Bhbi5vcmRpbmFsLWl0ZW0nKS5ub3QoXCIudG9vbGJhci1ncm91cGVyXCIpO1xuICAgICAgICBmb3IgKHZhciBpID0gMDsgaSA8IHRvb2xOb2Rlcy5sZW5ndGg7IGkrKykge1xuICAgICAgICAgICAgcGFyYW1zW2ldID0gdG9vbE5vZGVzW2ldLmRhdGFzZXQubW91bnRQb2ludDtcbiAgICAgICAgfVxuXG4gICAgICAgIHZhciBfdGhpcyA9IHRoaXM7XG4gICAgICAgIHZhciB1cmwgPSBfZ2V0UHJvamVjdFVybCgpICsgJy9hZG1pbi9tb3VudF9vcmRlcic7XG4gICAgICAgICQuYWpheCh7XG4gICAgICAgICAgICB0eXBlOiAnUE9TVCcsXG4gICAgICAgICAgICB1cmw6IHVybCxcbiAgICAgICAgICAgIGRhdGE6IHBhcmFtcyxcbiAgICAgICAgICAgIHN1Y2Nlc3M6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgICAgICAgICAkKCcjbWVzc2FnZXMnKS5ub3RpZnkoJ1Rvb2wgb3JkZXIgdXBkYXRlZCcsXG4gICAgICAgICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICAgICAgICAgIHN0YXR1czogJ2NvbmZpcm0nLFxuICAgICAgICAgICAgICAgICAgICAgICAgaW50ZXJ2YWw6IDUwMCxcbiAgICAgICAgICAgICAgICAgICAgICAgIHRpbWVyOiAyMDAwXG4gICAgICAgICAgICAgICAgICAgIH0pO1xuICAgICAgICAgICAgICAgIF90aGlzLmdldE5hdkpzb24oKTtcbiAgICAgICAgICAgIH0sXG5cbiAgICAgICAgICAgIGVycm9yOiBmdW5jdGlvbigpIHtcbiAgICAgICAgICAgICAgICAkKCcjbWVzc2FnZXMnKS5ub3RpZnkoJ0Vycm9yIHNhdmluZyB0b29sIG9yZGVyLicsXG4gICAgICAgICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICAgICAgICAgIHN0YXR1czogJ2Vycm9yJ1xuICAgICAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIH1cbiAgICAgICAgfSk7XG4gICAgfSxcblxuICAgIG9uVG9vbERyYWdTdGFydDogZnVuY3Rpb24ob2JqKSB7XG4gICAgICAgIC8vIHRoaXMgaXMgZG9uZSB3aXRoIGpRdWVyeSBpbnN0ZWFkIG9mIHJlbmRlcmluZyBkaWZmZXJlbnQgSFRNTCB3aXRoIHJlYWN0XG4gICAgICAgIC8vIGJlY2F1c2UgdGhhdCBtZWFucyB5b3UgcmUtcmVuZGVyIHRoZSBIVE1MIHdoaWxlIHRoZSBkcmFnIGlzIGhhcHBlbmluZ1xuICAgICAgICAvLyBhbmQgdGhlIGFjdHVhbCBkcmFnZ2luZyBkb2Vzbid0IHdvcmsgYW55IG1vcmVcbiAgICAgICAgdmFyIGRyYWdnaW5nX21vdW50X3BvaW50ID0gb2JqLnByb3BzLmNoaWxkcmVuLnByb3BzLm1vdW50X3BvaW50O1xuICAgICAgICAkKGBbZGF0YS1tb3VudC1wb2ludD0ke2RyYWdnaW5nX21vdW50X3BvaW50fV1gKS5jbG9zZXN0KCcucmVhY3QtZHJhZycpLmFkZENsYXNzKCdkcmFnZ2luZycpO1xuICAgIH0sXG5cbiAgICByZW5kZXI6IGZ1bmN0aW9uKCkge1xuICAgICAgICB2YXIgX3RoaXMgPSB0aGlzO1xuICAgICAgICB2YXIgbmF2QmFyU3dpdGNoID0gKHNob3dBZG1pbikgPT4ge1xuICAgICAgICAgICAgaWYgKHNob3dBZG1pbikge1xuICAgICAgICAgICAgICAgIHJldHVybiAoXG4gICAgICAgICAgICAgICAgICAgIDxBZG1pbk5hdlxuICAgICAgICAgICAgICAgICAgICAgICAgdG9vbHM9eyBfdGhpcy5zdGF0ZS5kYXRhLm1lbnUgfVxuICAgICAgICAgICAgICAgICAgICAgICAgaW5zdGFsbGFibGVUb29scz17IF90aGlzLnN0YXRlLmRhdGEuaW5zdGFsbGFibGVfdG9vbHMgfVxuICAgICAgICAgICAgICAgICAgICAgICAgZGF0YT17IF90aGlzLnN0YXRlLmRhdGEgfVxuICAgICAgICAgICAgICAgICAgICAgICAgb25Ub29sUmVvcmRlcj17IF90aGlzLm9uVG9vbFJlb3JkZXIgfVxuICAgICAgICAgICAgICAgICAgICAgICAgb25Ub29sRHJhZ1N0YXJ0PXsgX3RoaXMub25Ub29sRHJhZ1N0YXJ0IH1cbiAgICAgICAgICAgICAgICAgICAgICAgIGVkaXRNb2RlPXsgX3RoaXMuc3RhdGUudmlzaWJsZSB9XG4gICAgICAgICAgICAgICAgICAgICAgICBjdXJyZW50T3B0aW9uTWVudT17IF90aGlzLnN0YXRlLmN1cnJlbnRPcHRpb25NZW51IH1cbiAgICAgICAgICAgICAgICAgICAgICAgIG9uT3B0aW9uQ2xpY2s9eyBfdGhpcy5oYW5kbGVTaG93T3B0aW9uTWVudSB9XG4gICAgICAgICAgICAgICAgICAgICAgICBjdXJyZW50VG9vbE9wdGlvbnM9e3RoaXMuc3RhdGUuY3VycmVudFRvb2xPcHRpb25zfVxuICAgICAgICAgICAgICAgICAgICAvPlxuICAgICAgICAgICAgICAgICk7XG4gICAgICAgICAgICB9IGVsc2Uge1xuICAgICAgICAgICAgICAgIHJldHVybiAoXG4gICAgICAgICAgICAgICAgICAgIDxkaXY+XG4gICAgICAgICAgICAgICAgICAgICAgICA8Tm9ybWFsTmF2QmFyXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgaXRlbXM9eyBfdGhpcy5zdGF0ZS5kYXRhLm1lbnUgfVxuICAgICAgICAgICAgICAgICAgICAgICAgICAgIGluc3RhbGxhYmxlVG9vbHM9eyBfdGhpcy5zdGF0ZS5kYXRhLmluc3RhbGxhYmxlX3Rvb2xzIH1cbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAvPlxuICAgICAgICAgICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgICAgICAgICApO1xuICAgICAgICAgICAgfVxuICAgICAgICB9O1xuICAgICAgICB2YXIgbmF2QmFyID0gbmF2QmFyU3dpdGNoKHRoaXMuc3RhdGUudmlzaWJsZSk7XG5cbiAgICAgICAgdmFyIG1heF90b29sX2NvdW50ID0gXy5jaGFpbih0aGlzLnN0YXRlLmRhdGEubWVudSlcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLm1hcCgoaXRlbSkgPT4ge1xuICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgcmV0dXJuIGl0ZW0uY2hpbGRyZW4gPyBfLnBsdWNrKGl0ZW0uY2hpbGRyZW4sICd0b29sX25hbWUnKSA6IGl0ZW0udG9vbF9uYW1lXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgIH0pXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgIC5mbGF0dGVuKClcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLmNvdW50QnkoKVxuICAgICAgICAgICAgICAgICAgICAgICAgICAgICAudmFsdWVzKClcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLm1heCgpXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgIC52YWx1ZSgpO1xuICAgICAgICB2YXIgc2hvd19ncm91cGluZ190aHJlc2hvbGQgPSBtYXhfdG9vbF9jb3VudCA+IDE7XG5cbiAgICAgICAgcmV0dXJuIChcbiAgICAgICAgICAgIDxkaXZcbiAgICAgICAgICAgICAgICBjbGFzc05hbWU9eyAnbmF2X2FkbWluICd9PlxuICAgICAgICAgICAgICAgIHsgbmF2QmFyIH1cbiAgICAgICAgICAgICAgICA8ZGl2IGlkPSdiYXItY29uZmlnJz5cbiAgICAgICAgICAgICAgICAgICAge3Nob3dfZ3JvdXBpbmdfdGhyZXNob2xkICYmXG4gICAgICAgICAgICAgICAgICAgIDxHcm91cGluZ1RocmVzaG9sZFxuICAgICAgICAgICAgICAgICAgICAgICAgb25VcGRhdGVUaHJlc2hvbGQ9eyB0aGlzLm9uVXBkYXRlVGhyZXNob2xkIH1cbiAgICAgICAgICAgICAgICAgICAgICAgIGlzSGlkZGVuPXsgdGhpcy5zdGF0ZS52aXNpYmxlIH1cbiAgICAgICAgICAgICAgICAgICAgICAgIGluaXRpYWxWYWx1ZT17IHBhcnNlSW50KHRoaXMuc3RhdGUuZGF0YS5ncm91cGluZ190aHJlc2hvbGQpIH0vPiB9XG4gICAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICAgICAgPFRvZ2dsZUFkbWluQnV0dG9uXG4gICAgICAgICAgICAgICAgICAgIGhhbmRsZUJ1dHRvblB1c2g9eyB0aGlzLmhhbmRsZVRvZ2dsZUFkbWluIH1cbiAgICAgICAgICAgICAgICAgICAgdmlzaWJsZT17IHRoaXMuc3RhdGUudmlzaWJsZSB9Lz5cbiAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICApO1xuICAgIH1cbn0pO1xuIl19