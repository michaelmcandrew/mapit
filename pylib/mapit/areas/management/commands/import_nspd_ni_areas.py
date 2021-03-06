# This script is used to import Northern Ireland areas, from the data in the
# National Statistics Postcode Database.
# http://www.ons.gov.uk/about-statistics/geography/products/geog-products-postcode/nspd/
# 
# XXX This is incomplete, it needs to know which things have had boundary changes
# like import_boundary_line does. Hopefully just using new GSS codes by the time
# NI has any boundary changes.
#
# The fields of NSPD Open CSV file are:
#   Postcode (7), Postcode (8), Postcode (sp), Start date, End date, County,
#   council, ward, usertype, Easting, Northing, quality, SHA, IT cluster,
#   country, GOR, Stats region, Parliamentary constituency, Euro region,
#   TEC/LEC, Travel to Work area, Primary Care Org, NUTS, 1991 census ED,
#   1991 census ED, ED indicator, Pre-July 2006 SHA, LEA, Pre 2002 Health
#   Authority, 1991 ward code, 1991 ward code, 1998 ward code, 2005 stats ward,
#   OA code, OA indicator, CAS ward, National Park, SOA (Lower), Datazone, SOA
#   (Middle), Urban/rural, Urban/rural, Urban/rural, Intermediate, SOA (NI), OA
#   classification, Pre October 2006 PCO

import csv, re
from django.contrib.gis.geos import Point
from django.core.management.base import LabelCommand
from mapit.postcodes.models import Postcode
from mapit.areas.models import Area, Generation

class Command(LabelCommand):
    help = 'Creates/updates Northern Ireland areas, using the NSPD'
    args = '<NSPD CSV file>'

    def handle_label(self, file, **options):
        current_generation = Generation.objects.current()
        new_generation = Generation.objects.new()
        if not new_generation:
            raise Exception, "No new generation to be used for import!"

        euro_area, created = Area.objects.get_or_create(country='N', type='EUR',
            generation_low__lte=current_generation, generation_high__gte=current_generation,
            defaults = { 'generation_low': new_generation, 'generation_high': new_generation }
        )
        euro_area.generation_high = new_generation
        euro_area.save()
        euro_area.names.get_or_create(type='S', name='Northern Ireland')

        # Read in ward name -> electoral area name/area
        ni_eas = csv.reader(open('../../data/ni-electoral-areas.csv'))
        ni_eas.next()
        ward_to_electoral_area = {}
        e = {}
        for district, electoral_area, ward, dummy in ni_eas:
            if not district:
                district = last_district
            if not electoral_area:
                electoral_area = last_electoral_area
            last_district = district
            last_electoral_area = electoral_area
            if electoral_area not in e:
                ea = Area.objects.get_or_create_with_name(
                    country='N', type='LGE', name_type='M', name=electoral_area,
                )
                e[electoral_area] = ea
            ward_to_electoral_area.setdefault(district, {})[ward] = e[electoral_area]

        # Read in new ONS code to names
        snac = csv.reader(open('../../data/snac-2009-ni-cons2ward.csv'))
        snac.next()
        code_to_area = {}
        name_to_area = {}
        ward_to_parl = {}
        for parl_code, parl_name, ward_code, ward_name, district_code, district_name in snac:
            if district_name not in ward_to_electoral_area:
                raise Exception, "District %s is missing" % district_name
            if ward_name not in ward_to_electoral_area[district_name]:
                raise Exception, "Ward %s, district %s is missing" % (ward_name, district_name)

            ward_code = ward_code.replace(' ', '')

            if district_code not in code_to_area:
                district_area = Area.objects.get_or_create_with_code(
                    country='N', type='LGD', code_type='ons', code=district_code,
                )
                district_area.names.get_or_create(type='S', name=district_name)
                code_to_area[district_code] = district_area

            if ward_code not in code_to_area:
                ward_area = Area.objects.get_or_create_with_code(
                    country='N', type='LGW', code_type='ons', code=ward_code
                )
                ward_area.names.get_or_create(type='S', name=ward_name)
                ward_area.parent_area = ward_to_electoral_area[district_name][ward_name]
                ward_area.save()
                ward_area.parent_area.parent_area = code_to_area[district_code]
                ward_area.parent_area.save()
                code_to_area[ward_code] = ward_area

            if ward_code == '95S24': continue # Derryaghy

            if parl_code not in code_to_area:
                parl_area = Area.objects.get_or_create_with_code(
                    country='N', type='WMC', code_type='ons', code=parl_code,
                )
                parl_area.names.get_or_create(type='S', name=parl_name)
                new_code = re.sub('^7', 'N060000', parl_code)
                parl_area.codes.get_or_create(type='gss', code=new_code)
                code_to_area[parl_code] = parl_area
                name_to_area[parl_name] = parl_area
                
            ward_to_parl[ward_code] = code_to_area[parl_code]

        # Read in old SNAC for NI Assembly boundaries, still the same until 2011
        snac = csv.reader(open('../../data/snac-2003-ni-cons2ward.csv'))
        snac.next()
        ward_to_assembly = {}
        for parl_code, parl_name, ward_code, ward_name, district_code, district_name in snac:
            ward_code = ward_code.replace(' ', '')
            if 'NIE' + parl_code not in code_to_area:
                nia_area = Area.objects.get_or_create_with_name(
                    country='N', type='NIE', name_type='S', name=parl_name,
                )
                code_to_area['NIE' + parl_code] = nia_area
            ward_to_assembly[ward_code] = code_to_area['NIE' + parl_code]

        # The manual fix for the split ward in the 2010 boundaries
        derryaghy = csv.reader(open('../../data/Derryaghy-postcodes.csv'))
        derryaghy_fix = {}
        for postcode, parl_name in derryaghy:
            derryaghy_fix[postcode] = name_to_area[parl_name]

