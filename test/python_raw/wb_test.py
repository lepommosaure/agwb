#!/usr/bin/python3
import cbus
from agwb import MAIN
cbus.bus_delay(100)
mif=cbus.cbus_iface()
a=MAIN(mif,0)
print("Test the ID")
print ("ID read:"+ hex(a.ID.read()))
print ("VER read:"+ hex(a.VER.read()))
cbus.bus_delay(250)
print("LINKS0 ID read:"+hex(a.LINKS[0].ID.read()))
print("LINKS0 VER read:"+hex(a.LINKS[0].VER.read()))
cbus.bus_delay(250)
print("LINKS0 STATUS read:"+hex(a.LINKS[0].STATUS.read()))
cbus.bus_delay(250)
print("Initial value of MAIN.CTRL:"+hex(a.CTRL.read()))
print("LINKS0 CTRL.START write")
a.LINKS[0].CTRL.START.write(1)
cbus.bus_delay(250)
print("LINKS4 STATUS read:"+hex(a.LINKS[4].STATUS.read()))
cbus.bus_delay(250)
print("Now we test bitfields")
print("LINKS4 CTRL.START write")
a.LINKS[4].CTRL.START.write(1)
a.CTRL.CLK_ENABLE.write(1)
cbus.bus_delay(30)
a.CTRL.CLK_FREQ.write(0xc)
cbus.bus_delay(30)
a.CTRL.PLL_RESET.write(1)
cbus.bus_delay(30)
a.CTRL.CLK_ENABLE.write(0)
cbus.bus_delay(30)
a.CTRL.CLK_FREQ.write(0x5)
cbus.bus_delay(30)
a.CTRL.PLL_RESET.write(0)
print("Now we test the blackbox")
a.EXTERN[0].reg[1].write(0x5)
print("EXTERN[0] REG1 read:"+hex(a.EXTERN[0].reg[1].read()))
a.EXTERN[1].reg[2].write(0x76)
print("EXTERN[1] REG2 read:"+hex(a.EXTERN[1].reg[2].read()))
print("And again we read the LINKS1 ID and version")
print("LINKS1 ID read:"+hex(a.LINKS[0].ID.read()))
print("LINKS1 VER read:"+hex(a.LINKS[0].VER.read()))
a.TEST_OUT[1].write(0x13)
print("TEST_IN_i(0):"+hex(a.TEST_IN[0].read()))
print("TEST_IN_i(1):"+hex(a.TEST_IN[1].read()))
print("TEST_IN_i(2):"+hex(a.TEST_IN[2].read()))
cbus.bus_delay(3000)



