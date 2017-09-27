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
/* eslint camelcase: 0 */
/* globals ContextMenu ToolTip */
'use strict';

/**
* Gets the current project url.
* @param {boolean} rest - Return a "rest" version of the url.
* @return {string} - Project Url
*/
var _getProjectUrl = function(rest = true) {
    var nbhd;
    var proj;
    var nbhd_proj;
    var identClasses = document.getElementById('page-body').className.split(' ');
    var basePath = rest ? '/rest/' : '/';
    for (let cls of identClasses) {
        if (cls.indexOf('project-') === 0) {
            proj = cls.slice('project-'.length);
        }
    }
    nbhd = window.location.pathname.split('/')[1];
    if (proj === '--init--') {
        nbhd_proj = nbhd;
    } else {
        nbhd_proj = `${nbhd}/${proj}`;
    }
    return basePath + nbhd_proj;
};

const ToolsPropType = React.PropTypes.shape({
    mount_point: React.PropTypes.string,
    name: React.PropTypes.string.isRequired,
    url: React.PropTypes.string.isRequired,
    is_anchored: React.PropTypes.bool.isRequired,
    tool_name: React.PropTypes.string.isRequired,
    icon: React.PropTypes.string,
    children: React.PropTypes.array,
    admin_options: React.PropTypes.array
});

/**
 * A single NavBar item.

 * @constructor
 */
var NavBarItem = React.createClass({
    propTypes: {
        name: React.PropTypes.string.isRequired,
        url: React.PropTypes.string.isRequired,
        currentOptionMenu: React.PropTypes.object,
        isGrouper: React.PropTypes.bool,
        mount_point: React.PropTypes.string,
        onOptionClick: React.PropTypes.func.isRequired,
        options: React.PropTypes.array,
        handleType: React.PropTypes.string,
        is_anchored: React.PropTypes.bool
    },

    render: function() {
        var divClasses = "tb-item tb-item-edit";
        var spanClasses = this.props.handleType + " ordinal-item";

        if (this.props.is_anchored) {
            divClasses += " anchored";
        }
        if (this.props.isGrouper) {
            spanClasses += " toolbar-grouper";
        }

        return (
            <div className={divClasses}>
                <ToolTip targetSelector=".anchored .draggable-handle"
                         position="top"
                         theme="tooltipster-default"
                         delay={250}/>
                <ToolTip targetSelector=".anchored .draggable-handle-sub"
                         position="right"
                         theme="tooltipster-default"
                         delay={250}/>
                <a>
                    {!_.isEmpty(this.props.options) &&
                    <i className='config-tool fa fa-cog' onClick={this.handleOptionClick}> </i>}
                    <span
                        className={spanClasses}
                        data-mount-point={this.props.mount_point}
                        title={this.props.is_anchored ? 'This item cannot be moved.' : ''}>
                        {this.props.name}
                    </span>
                </a>
                {this.props.currentOptionMenu.tool &&
                this.props.currentOptionMenu.tool === this.props.mount_point &&
                <ContextMenu {...this.props} items={this.props.options} onOptionClick={this.props.onOptionClick}/>}
            </div>
        );
    },

    handleOptionClick: function(event) {
        this.props.onOptionClick(this.props.mount_point);
    }
});

/**
 * An input component that updates the NavBar's grouping threshold.

 * @constructor
 */
var GroupingThreshold = React.createClass({
    propTypes: {
        initialValue: React.PropTypes.number.isRequired,
        isHidden: React.PropTypes.bool,
        onUpdateThreshold: React.PropTypes.func
    },
    getInitialState: function() {
        return {
            value: this.props.initialValue
        };
    },

    handleChange: function(event) {
        this.setState({
            value: event.target.value
        });
        this.props.onUpdateThreshold(event);
    },

    render: function() {
        return (
            <div>
                {Boolean(this.props.isHidden) &&
                <div id='threshold-config'>
            <span>
              <label htmlFor='threshold-input'>Grouping Threshold</label>
                <ToolTip targetSelector="#threshold-input" position="top" contentAsHTML/>
                <input type='number' name='threshold-input' id="threshold-input"
                       title='When you have multiple tools of the same type,
                             <u>this number</u> determines if they will fit in the navigation
                             bar or be grouped into a dropdown.'
                       value={this.state.value}
                       onChange={this.handleChange}
                       min='1' max='50'
                />
              </span>
                </div>}
            </div>
        );
    }
});

/**
 * The NavBar when in "Normal" mode.

 * @constructor
 */
var NormalNavItem = React.createClass({
    propTypes: {
        name: React.PropTypes.string.isRequired,
        url: React.PropTypes.string.isRequired,
        children: React.PropTypes.object,
        classes: React.PropTypes.string
    },
    render: function() {
        return (
            <li key={`tb-norm-${_.uniqueId()}`}>
                <a href={this.props.url} className={this.props.classes}>
                    {this.props.name}
                </a>
                {this.props.children}
            </li>
        );
    }
});

/**
 * Toggle Button

 * @constructor
 */
var ToggleAddNewTool = React.createClass({
    propTypes: {
        installableTools: React.PropTypes.arrayOf(
            React.PropTypes.shape({
                text: React.PropTypes.string.isRequired,
                href: React.PropTypes.string,
                tooltip: React.PropTypes.string
            })
        ).isRequired
    },
    getInitialState: function() {
        return {
            visible: false
        };
    },
    handleToggle: function() {
        this.setState({
            visible: !this.state.visible
        });
    },
    render: function() {
        return (
            <div>
                <a onClick={this.handleToggle} className="add-tool-toggle">
                    Add New...
                </a>
                {this.state.visible &&
                    <ContextMenu
                        {...this.props}
                        classes={['admin_modal']}
                        onOptionClick={this.handleToggle}
                        items={this.props.installableTools}
                    />
                }
            </div>
        );
    }
});

/**
 * The NavBar when in "Normal" mode.

 * @constructor
 */
var NormalNavBar = React.createClass({
    propTypes: {
        items: React.PropTypes.arrayOf(ToolsPropType).isRequired,
        installableTools: React.PropTypes.arrayOf(
            React.PropTypes.shape({
                text: React.PropTypes.string.isRequired,
                href: React.PropTypes.string,
                tooltip: React.PropTypes.string
            })
        ).isRequired
    },

    buildMenu: function(item, i) {
        let classes = window.location.pathname.startsWith(item.url) ? 'active-nav-link' : '';

        var subMenu;
        if (item.children) {
            subMenu = item.children.map(this.buildMenu);
        }
        return (
            <NormalNavItem url={item.url} name={item.name} classes={classes} key={`normal-nav-${_.uniqueId()}`}>
                <ul>
                    {subMenu}
                </ul>
            </NormalNavItem>
        );
    },

    render: function() {
        var listItems = this.props.items.map(this.buildMenu);
        return (
            <ul
                id="normal-nav-bar"
                className="dropdown">
                {listItems}
                <li id="add-tool-container">
                    <ToggleAddNewTool installableTools={this.props.installableTools}/>
                </li>
            </ul>
        );
    }
});

/**
 * The NavBar when in "Admin" mode.
 * @constructor
 */
var AdminNav = React.createClass({
    propTypes: {
        tools: React.PropTypes.arrayOf(ToolsPropType),
        currentOptionMenu: React.PropTypes.object,
        installableTools: React.PropTypes.arrayOf(
            React.PropTypes.shape({
                text: React.PropTypes.string.isRequired,
                href: React.PropTypes.string,
                tooltip: React.PropTypes.string
            })
        ),
        onOptionClick: React.PropTypes.func.isRequired
    },

    buildMenu: function(items, isSubMenu = false) {
        var _this = this;
        var [tools, anchoredTools, endTools] = [[], [], []];
        var subMenu;
        var childOptionsOpen;
        var _handle;
        var toolList;
        var isAnchored;
        for (let item of items) {
            if (item.children) {
                subMenu = this.buildMenu(item.children, true);
            } else {
                subMenu = null;
            }

            _handle = isSubMenu ? "draggable-handle-sub" : 'draggable-handle';
            if (item.mount_point === 'admin') {
                // force admin to end, just like 'Project.sitemap()' does
                toolList = endTools;
                isAnchored = true;
            } else if (item.is_anchored) {
                toolList = anchoredTools;
                isAnchored = true;
            } else {
                toolList = tools;
                isAnchored = false;
            }
            let coreItem = (<NavBarItem
                {..._this.props}
                mount_point={item.mount_point}
                name={item.name}
                handleType={_handle}
                isGrouper={item.children && item.children.length > 0}
                url={item.url}
                key={'tb-item-' + _.uniqueId()}
                is_anchored={isAnchored}
                options={item.admin_options}
            />);
            if (subMenu) {
                childOptionsOpen = _.contains(_.pluck(item.children, 'mount_point'),
                    this.props.currentOptionMenu.tool);

                toolList.push(<NavBarItemWithSubMenu
                    key={_.uniqueId()}
                    tool={coreItem}
                    subMenu={subMenu}
                    childOptionsOpen={childOptionsOpen}
                />);
            } else {
                toolList.push(coreItem);
            }
        }

        return (
            <div className='react-drag'>
                {anchoredTools}
                <ReactReorderable
                    key={'reorder-' + _.uniqueId()}
                    handle={"." + _handle}
                    mode={isSubMenu ? 'list' : 'grid'}
                    onDragStart={_this.props.onToolDragStart}
                    onDrop={_this.props.onToolReorder}>
                    {tools}
                </ReactReorderable>
                {endTools}
                {!isSubMenu && <div id="add-tool-container" className="unlocked-container">
                    <ToggleAddNewTool installableTools={this.props.installableTools}/>
                </div>}
            </div>
        );
    },

    render: function() {
        var tools = this.buildMenu(this.props.tools);
        return <div>{tools}</div>;
    }
});

var NavBarItemWithSubMenu = React.createClass({
    propTypes: {
        subMenu: React.PropTypes.node,
        childOptionsOpen: React.PropTypes.bool,
        tool: React.PropTypes.node
    },
    render: function() {
        return (
            <div className={"tb-item-container" + (this.props.childOptionsOpen ? " child-options-open" : "")}>
                {this.props.tool}
                {this.props.subMenu &&
                <AdminItemGroup key={_.uniqueId()}>
                    {this.props.subMenu}
                </AdminItemGroup>
                    }
            </div>
        );
    }
});

/**
 * The NavBar when in "Admin" mode.
 * @constructor
 */
var AdminItemGroup = React.createClass({
    propTypes: {
        children: React.PropTypes.object
    },
    render: function() {
        return (
            <div className="tb-item-grouper">
                {this.props.children}
            </div>
        );
    }
});

/**
 * The button that toggles NavBar modes.

 * @constructor
 */
var ToggleAdminButton = React.createClass({
    propTypes: {
        handleButtonPush: React.PropTypes.func,
        visible: React.PropTypes.bool
    },
    render: function() {
        var classes = this.props.visible ? 'fa fa-unlock' : 'fa fa-lock';
        return (
            <button id='toggle-admin-btn' onClick={this.props.handleButtonPush} className='admin-toolbar-right'>
                <i className={classes}> </i>
            </button>
        );
    }
});

/**
 * The main "controller view" of the NavBar.

 * @constructor
 * @param {object} initialData
 */
var Main = React.createClass({
    propTypes: {
        initialData: React.PropTypes.shape({
            menu: React.PropTypes.arrayOf(ToolsPropType),
            installableTools: React.PropTypes.array,
            grouping_threshold: React.PropTypes.number.isRequired
        }),
        installableTools: React.PropTypes.array
    },
    getInitialState: function() {
        return {
            data: this.props.initialData,
            visible: true,
            currentOptionMenu: {
                tool: null
            }
        };
    },

    /**
     * When invoked, this updates the state with the latest data from the server.
     */
    getNavJson: function() {
        $.get(`${_getProjectUrl(false)}/_nav.json?admin_options=1`, function(result) {
            if (this.isMounted()) {
                this.setState({
                    data: result
                });
            }
        }.bind(this));
    },
    /**
     * Handles the locking and unlocking of the NavBar
     */
    handleToggleAdmin: function() {
        this.setState({
            visible: !this.state.visible
        });
    },

    handleShowOptionMenu: function(mount_point) {
        this.setState({
            currentOptionMenu: {
                tool: mount_point
            }
        });
    },

    /**
     * Handles the changing of the NavBars grouping threshold.
     * @param {object} event Fired when the threshold changes
     * @return {boolean} False
     */
    onUpdateThreshold: function(event) {
        var thres = event.target.value;
        var url = `${_getProjectUrl()}/admin/configure_tool_grouping`;
        var csrf = $.cookie('_session_id');
        var data = {
            _session_id: csrf,
            grouping_threshold: thres
        };
        $.post(url, data, () => this.getNavJson());
        return false;
    },

    /**
     * Handles the sending and updating tool ordinals.
     */
    onToolReorder: function() {
        $('.react-drag.dragging').removeClass('dragging');

        let params = {_session_id: $.cookie('_session_id')};
        let toolNodes = $(ReactDOM.findDOMNode(this)).find('span.ordinal-item').not(".toolbar-grouper");
        for (let i = 0; i < toolNodes.length; i++) {
            params[i] = toolNodes[i].dataset.mountPoint;
        }

        let _this = this;
        let url = _getProjectUrl() + '/admin/mount_order';
        $.ajax({
            type: 'POST',
            url: url,
            data: params,
            success: function() {
                $('#messages').notify('Tool order updated',
                    {
                        status: 'confirm',
                        interval: 500,
                        timer: 2000
                    });
                _this.getNavJson();
            },

            error: function() {
                $('#messages').notify('Error saving tool order.',
                    {
                        status: 'error'
                    });
            }
        });
    },

    onToolDragStart: function(obj) {
        // this is done with jQuery instead of rendering different HTML with react
        // because that means you re-render the HTML while the drag is happening
        // and the actual dragging doesn't work any more
        var dragging_mount_point = obj.props.children.props.mount_point;
        $(`[data-mount-point="${dragging_mount_point}"]`).closest('.react-drag').addClass('dragging');
    },

    render: function() {
        var _this = this;
        var navBarSwitch = showAdmin => {
            var navbar;
            if (showAdmin) {
                navbar = (<AdminNav
                    tools={_this.state.data.menu}
                    installableTools={_this.state.data.installable_tools}
                    data={_this.state.data}
                    onToolReorder={_this.onToolReorder}
                    onToolDragStart={_this.onToolDragStart}
                    editMode={_this.state.visible}
                    currentOptionMenu={_this.state.currentOptionMenu}
                    onOptionClick={_this.handleShowOptionMenu}
                    currentToolOptions={this.state.currentToolOptions}
                />);
            } else {
                navbar = (<div>
                    <NormalNavBar
                        items={_this.state.data.menu}
                        installableTools={_this.state.data.installable_tools}
                    />
                </div>);
            }
            return navbar;
        };
        var navBar = navBarSwitch(this.state.visible);

        var max_tool_count = _.chain(this.state.data.menu)
                             .map(item => {
                                 return item.children ? _.pluck(item.children, 'tool_name') : item.tool_name;
                             })
                             .flatten()
                             .countBy()
                             .values()
                             .max()
                             .value();
        var show_grouping_threshold = max_tool_count > 1;

        return (
            <div>
                {navBar}
                <div id='bar-config'>
                    {show_grouping_threshold &&
                    <GroupingThreshold
                        onUpdateThreshold={this.onUpdateThreshold}
                        isHidden={this.state.visible}
                        initialValue={parseInt(this.state.data.grouping_threshold, 10)}/>}
                </div>
                <ToggleAdminButton
                    handleButtonPush={this.handleToggleAdmin}
                    visible={this.state.visible}/>
            </div>
        );
    }
});
