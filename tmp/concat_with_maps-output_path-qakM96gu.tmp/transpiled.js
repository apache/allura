
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


'use strict';

var _createClass = (function () { function defineProperties(target, props) { for (var i = 0; i < props.length; i++) { var descriptor = props[i]; descriptor.enumerable = descriptor.enumerable || false; descriptor.configurable = true; if ('value' in descriptor) descriptor.writable = true; Object.defineProperty(target, descriptor.key, descriptor); } } return function (Constructor, protoProps, staticProps) { if (protoProps) defineProperties(Constructor.prototype, protoProps); if (staticProps) defineProperties(Constructor, staticProps); return Constructor; }; })();

function _classCallCheck(instance, Constructor) { if (!(instance instanceof Constructor)) { throw new TypeError('Cannot call a class as a function'); } }

function _inherits(subClass, superClass) { if (typeof superClass !== 'function' && superClass !== null) { throw new TypeError('Super expression must either be null or a function, not ' + typeof superClass); } subClass.prototype = Object.create(superClass && superClass.prototype, { constructor: { value: subClass, enumerable: false, writable: true, configurable: true } }); if (superClass) Object.setPrototypeOf ? Object.setPrototypeOf(subClass, superClass) : subClass.__proto__ = superClass; }

var ToolTip = (function (_React$Component) {
    _inherits(ToolTip, _React$Component);

    function ToolTip(props) {
        _classCallCheck(this, ToolTip);

        _React$Component.call(this, props);
    }

    ToolTip.prototype.componentDidMount = function componentDidMount() {
        var _this = this;
        $(".react-tooltip").tooltipster({
            animation: _this.props.animation,
            speed: _this.props.speed,
            delay: _this.props.delay,
            theme: _this.props.theme,
            contentAsHTML: _this.props.contentAsHTML,
            trigger: _this.props.trigger,
            position: _this.props.position,
            multiple: _this.props.multiple,
            iconCloning: false,
            maxWidth: _this.props.maxWidth
        });
    };

    _createClass(ToolTip, null, [{
        key: 'propTypes',
        value: {
            animation: React.PropTypes.string,
            speed: React.PropTypes.number,
            position: React.PropTypes.string,
            contentAsHTML: React.PropTypes.bool,
            delay: React.PropTypes.number,
            theme: React.PropTypes.string,
            maxWidth: React.PropTypes.number,
            trigger: React.PropTypes.string,
            multiple: React.PropTypes.bool,
            classes: React.PropTypes.array,
            text: React.PropTypes.string.isRequired,
            href: React.PropTypes.string.isRequired,
            toolTip: React.PropTypes.string
        },
        enumerable: true
    }, {
        key: 'defaultProps',
        value: {
            animation: 'fade',
            speed: 150,
            delay: 0,
            maxWidth: 300,
            multiple: true,
            contentAsHTML: false,
            position: 'left',
            trigger: 'hover',
            classes: [],
            theme: 'tooltipster-light'
        },
        enumerable: true
    }]);

    return ToolTip;
})(React.Component);

var ToolTipLink = (function (_ToolTip) {
    _inherits(ToolTipLink, _ToolTip);

    function ToolTipLink(props) {
        _classCallCheck(this, ToolTipLink);

        _ToolTip.call(this, props);
    }

    ToolTipLink.prototype.render = function render() {
        var classes = this.props.classes.join(' ') + " react-tooltip";
        return React.createElement(
            'a',
            { href: this.props.href, className: classes, title: this.props.toolTip },
            this.props.text
        );
    };

    return ToolTipLink;
})(ToolTip);
//# sourceMappingURL=transpiled.map