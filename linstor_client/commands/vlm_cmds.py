from __future__ import print_function

import linstor.sharedconsts as apiconsts
import linstor_client.argparse.argparse as argparse


from linstor import SizeCalc
from linstor.responses import Resource
from linstor_client import Table
from linstor_client.commands import Commands
from linstor_client.utils import Output
from linstor_client.consts import Color


class VolumeCommands(Commands):

    def setup_commands(self, parser):
        """

        :param parser:
        :return:
        """
        subcmds = [
            Commands.Subcommands.List,
            Commands.Subcommands.SetProperty,
            Commands.Subcommands.ListProperties
        ]

        vlm_parser = parser.add_parser(
            Commands.VOLUME,
            aliases=['v'],
            formatter_class=argparse.RawTextHelpFormatter,
            description="Resouce subcommands")
        vlm_sub = vlm_parser.add_subparsers(
            title="volume commands",
            metavar="",
            description=Commands.Subcommands.generate_desc(subcmds)
        )

        # list volumes
        p_lvlms = vlm_sub.add_parser(
            Commands.Subcommands.List.LONG,
            aliases=[Commands.Subcommands.List.SHORT],
            description='Prints a list of all volumes.'
        )
        p_lvlms.add_argument('-p', '--pastable', action="store_true", help='Generate pastable output')
        p_lvlms.add_argument(
            '-n', '--nodes',
            nargs='+',
            type=str,
            help='Filter by list of nodes').completer = self.node_completer
        p_lvlms.add_argument('-s', '--storpools', nargs='+', type=str,
                             help='Filter by list of storage pools').completer = self.storage_pool_completer
        p_lvlms.add_argument(
            '-r', '--resources',
            nargs='+',
            type=str,
            help='Filter by list of resources').completer = self.resource_completer
        p_lvlms.set_defaults(func=self.list_volumes)

        # show properties
        p_lp = vlm_sub.add_parser(
            Commands.Subcommands.ListProperties.LONG,
            aliases=[Commands.Subcommands.ListProperties.SHORT],
            description="Prints all properties of the given volume.")
        p_lp.add_argument('-p', '--pastable', action="store_true", help='Generate pastable output')
        p_lp.add_argument(
            'node_name',
            help="Node name where the resource is deployed.").completer = self.node_completer
        p_lp.add_argument(
            'resource_name',
            help="Resource name").completer = self.resource_completer
        p_lp.add_argument('volume_number', type=int, help="Volume number")
        p_lp.set_defaults(func=self.print_props)

        # set properties
        p_setprop = vlm_sub.add_parser(
            Commands.Subcommands.SetProperty.LONG,
            aliases=[Commands.Subcommands.SetProperty.SHORT],
            description='Sets properties for the given volume on the given resource.')
        p_setprop.add_argument(
            'node_name',
            type=str,
            help='Node name where resource is deployed.').completer = self.node_completer
        p_setprop.add_argument(
            'resource_name',
            type=str,
            help='Name of the resource'
        ).completer = self.resource_completer
        p_setprop.add_argument('volume_number', type=int, help='Volume number')
        Commands.add_parser_keyvalue(p_setprop, "volume")
        p_setprop.set_defaults(func=self.set_props)

        self.check_subcommands(vlm_sub, subcmds)

    @staticmethod
    def get_volume_state(volume_states, volume_nr):
        for volume_state in volume_states:
            if volume_state.number == volume_nr:
                return volume_state
        return None

    @staticmethod
    def volume_state_cell(vlm_state, rsc_flags, vlm_flags):
        """
        Determains the status of a drbd volume for table display.

        :param vlm_state: vlm_state proto
        :param rsc_flags: rsc flags
        :param vlm_flags: vlm flags
        :return: A tuple (state_text, color)
        """
        tbl_color = None
        state_prefix = 'Resizing, ' if apiconsts.FLAG_RESIZE in vlm_flags else ''
        state = state_prefix + "Unknown"
        if vlm_state and vlm_state.disk_state:
            disk_state = vlm_state.disk_state

            if disk_state == 'DUnknown':
                state = state_prefix + "Unknown"
                tbl_color = Color.YELLOW
            elif disk_state == 'Diskless':
                if apiconsts.FLAG_DISKLESS not in rsc_flags:  # unintentional diskless
                    state = state_prefix + disk_state
                    tbl_color = Color.RED
                else:
                    state = state_prefix + disk_state  # green text
            elif disk_state in ['Inconsistent', 'Failed', 'To: Creating', 'To: Attachable', 'To: Attaching']:
                state = state_prefix + disk_state
                tbl_color = Color.RED
            elif disk_state in ['UpToDate', 'Created', 'Attached']:
                state = state_prefix + disk_state  # green text
            else:
                state = state_prefix + disk_state
                tbl_color = Color.YELLOW
        else:
            tbl_color = Color.YELLOW
        return state, tbl_color

    @classmethod
    def show_volumes(cls, args, lstmsg):
        tbl = Table(utf8=not args.no_utf8, colors=not args.no_color, pastable=args.pastable)
        tbl.add_column("Node")
        tbl.add_column("Resource")
        tbl.add_column("StoragePool")
        tbl.add_column("VolumeNr")
        tbl.add_column("MinorNr")
        tbl.add_column("DeviceName")
        tbl.add_column("Allocated")
        tbl.add_column("InUse", color=Output.color(Color.DARKGREEN, args.no_color))
        tbl.add_column("State", color=Output.color(Color.DARKGREEN, args.no_color), just_txt='>')

        rsc_state_lkup = {x.node_name + x.name: x for x in lstmsg.resource_states}

        for rsc in lstmsg.resources:
            rsc_state = rsc_state_lkup.get(rsc.node_name + rsc.name)
            rsc_usage = ""
            if rsc_state:
                if rsc_state.in_use:
                    rsc_usage = tbl.color_cell("InUse", Color.GREEN)
                else:
                    rsc_usage = "Unused"
            for vlm in rsc.volumes:
                vlm_state = cls.get_volume_state(
                    rsc_state.volume_states,
                    vlm.number
                ) if rsc_state else None
                state_txt, color = cls.volume_state_cell(vlm_state, rsc.flags, vlm.flags)
                state = tbl.color_cell(state_txt, color) if color else state_txt
                vlm_drbd_data = vlm.drbd_data
                tbl.add_row([
                    rsc.node_name,
                    rsc.name,
                    vlm.storage_pool_name,
                    str(vlm.number),
                    str(vlm_drbd_data.drbd_volume_definition.minor) if vlm_drbd_data else "",
                    vlm.device_path,
                    SizeCalc.approximate_size_string(vlm.allocated_size) if vlm.allocated_size else "",
                    rsc_usage,
                    state
                ])

        tbl.show()

    def list_volumes(self, args):
        lstmsg = self._linstor.volume_list(args.nodes, args.storpools, args.resources)

        return self.output_list(args, lstmsg, VolumeCommands.show_volumes)

    @classmethod
    def _props_list(cls, args, lstmsg):
        if lstmsg and lstmsg.resources:
            rsc = lstmsg.resources[0]  # type: Resource
            vlms = [x for x in rsc.volumes if x.number == args.volume_number]
            if vlms:
                return [vlms[0].properties]
        return []

    def print_props(self, args):
        lstmsg = self._linstor.volume_list(filter_by_nodes=[args.node_name], filter_by_resources=[args.resource_name])

        return self.output_props_list(args, lstmsg, self._props_list)

    def set_props(self, args):
        args = self._attach_aux_prop(args)
        mod_prop_dict = Commands.parse_key_value_pairs([args.key + '=' + args.value])
        replies = self._linstor.volume_modify(
            args.node_name,
            args.resource_name,
            args.volume_number,
            mod_prop_dict['pairs'],
            mod_prop_dict['delete']
        )
        return self.handle_replies(args, replies)
