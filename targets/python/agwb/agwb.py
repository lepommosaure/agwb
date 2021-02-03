#!/usr/bin/python3
"""@package docstring
Documentation for agwb.py module

Written by Wojciech M. Zabolotny
wzab01<at>gmail.com 18-20.06.2019
added support for extended interface:
wzab01<at>gmail.com 2.02.2021

The agwb.py module is a helper that provides
access to hierarchy of blocks/registers/bitfields
generated by addr_gen_wb environment, from
the pure Python code, via a simple interface.
The interface must provide two methods:

read(self,address) that returns 32-bit value
write(self,address,value) that writes such a value

The extended interface (with cached write and read
accesses and support for optimized bitfields
handling and read-modify-write) should provide
additional methods:

writex(self,address,value) - that only schedules 
       a write (unless the operation list is full)
readx(self,address) - that returns the "future" 
       object with "val" field (or method) that returns
       the value (possibly triggering dispatch if necessary)
rmw(self,address=none,mask=0,value=0) - schedules the read-modify-write
       operation defined as follows
       X:= (X and ~mask) | (value and mask)
       The consecutive operations on the same address are aggregated.
       the "value" and "mask" are updated.
       If any other operation (read, write, readx, writes) or
       rmw to anothe address is called, the pending rmw must 
       be finalized.
       Also calling rmw without arguments finalizes the pending RMW.
dispatch() - executes the accumulated list of operations
      (the list may be executed automatically, if it grows
      to its full possible length).
"""

class BitField(object):
    """Class delivering an object used to describe the bitfield.

    Its fields contain certain precalculated values supporting quick
    handling of read and write access to the field.
    That class does not provide any methods.
    Only fields are used.
    """

    def __init__(self, msb, lsb, is_signed):
        self.lsb = lsb
        self.msb = msb
        if is_signed:
            self.sign_mask = 1 << (msb - lsb)
            self.vmin = -self.sign_mask
            self.vmax = self.sign_mask - 1
        else:
            self.vmin = 0
            self.vmax = (1 << (msb - lsb + 1)) - 1
            self.sign_mask = 0
        self.mask = ((1 << (msb + 1)) - 1) ^ ((1 << lsb) - 1)

class _BitFieldFuture(object):
    """Class enabling delayed access to the value read from the bitfield
    """
    def __init__(self, rfut, bf):
    	self.rfut = rfut
    	self.bf = bf
    	
    def __getattr__(self,name):
        if name == "val":
            rval = self.rfut.val & self.bf.mask
            rval >>= self.bf.lsb
            if self.bf.sign_mask:
                if rval & self.bf.sign_mask:
                    rval -= self.bf.sign_mask << 1
            return rval
        else:
            raise Exception("Only val field is available")

class _BitFieldAccess(object):
    """Class providing a versatile object supporting  read/write access to any bitfield.

    The details of the particular bitfield are hidden in the
    BitField object passed via bf argument.
    """

    def __init__(self, iface, base, bf):
        self.x__iface = iface
        self.x__base = base
        self.x__bf = bf

    def read(self):
        """ Simple read method. Does not use any access optimization.
            The read is performed immediately, the result is
            masked, shifted and returned as integer. 
        """
        rval = self.x__iface.read(self.x__base)
        rval &= self.x__bf.mask
        rval >>= self.x__bf.lsb
        if self.x__bf.sign_mask:
            if rval & self.x__bf.sign_mask:
                rval -= self.x__bf.sign_mask << 1
        return rval

    def write(self, value):
        """ Simple write method. Does not use any access optimization.
            The write is performed immediately.
            Please note, that access to each bitfield generates
            a strobe pulse for the whole register (if strobe is implemented).
        """
        # Check if the value to be stored is correct
        if (value < self.x__bf.vmin) or (value > self.x__bf.vmax):
            raise Exception("Value doesn't fit in the bitfield")
        # If the bitfield is signed, convert the negative values
        if self.x__bf.sign_mask:
            if value < 0:
                value += self.x__bf.sign_mask << 1
                print("final value: " + str(value))
        # Read the whole register
        rval = self.x__iface.read(self.x__base)
        # Mask the bitfield
        rval |= self.x__bf.mask
        rval ^= self.x__bf.mask
        # Shift the new value
        value = value << self.x__bf.lsb
        value &= self.x__bf.mask
        rval |= value
        self.x__iface.write(self.x__base, rval)

    def readx(self):
        """ Optimized read method. Schedules reading of the register.
            The "future" object is returned.
            When the "val" field in the returned value is accessed,
            The read is performed immediately (if not dispatched yet),
            and the result is masked, shifted and returned. 
        """    
        rval = self.x__iface.readx(self.x__base)
        return _BitFieldFuture(rval,self.x__bf)

    def writex(self, value, now=True):
        """ Optimized write method. The write is translated into the
            rmw command. Multiple writex commands to bitfields located
            in the same register are aggregated into a single rmw,
            unless "now" is True.
            Reading of the register is scheduled after the first writex
            is executed.
            If "now" is True, or another operation than rmw to the same
            register is executed, the write is scheduled with current
            mask and value, resulting from rmws aggregated up to now.
        """
        # Check if the value to be stored is correct
        if (value < self.x__bf.vmin) or (value > self.x__bf.vmax):
            raise Exception("Value doesn't fit in the bitfield")
        # If the bitfield is signed, convert the negative values
        if self.x__bf.sign_mask:
            if value < 0:
                value += self.x__bf.sign_mask << 1
                print("final value: " + str(value))
        # Calculate the shifted value
        value = value << self.x__bf.lsb
        # Schedule the RMW operation        
        self.x__iface.rmw(self.x__base, self.x__bf.mask, value)        
        # If now is true, finalize the current RMW
        if now:
            self.x__iface.rmw()

class Vector(object):
    """Class describing the vector of registers or subblocks.

    It provides only a __getitem__ method that allows to access the particular object
    in a vector (the object is created on the fly, when it is needed).
    """

    def __init__(self, iface, base, nitems, margs):
        self.iface = iface
        self.base = base
        self.mclass = margs[0]
        self.args = None
        if len(margs) > 1:
            self.args = margs[1]
        self.nitems = nitems

    def __getitem__(self, key):
        if key >= self.nitems:
            raise Exception("Access outside the vector")
        if self.args != None:
            return self.mclass(
                self.iface, self.base + key * self.mclass.x__size, self.args
            )
        return self.mclass(self.iface, self.base + key * self.mclass.x__size)


class Block(object):
    """Class describing the blocks handled by addr_gen_wb-generated code.

    The Python backend generates derived classes, with class fields
    corresponding to subblocks or registers.
    """

    x__is_blackbox = False
    x__size = 1
    x__fields = {}

    def __init__(self, iface, base):
        """base is the base address for the given block. """
        self.x__base = base
        self.x__iface = iface

    def __dir__(self):
        return self.x__fields.keys()

    def __getattr__(self, name):
        f_i = self.x__fields[name]
        if len(f_i) == 3:
            return Vector(self.x__iface, self.x__base + f_i[0], f_i[1], f_i[2])
        elif len(f_i) == 2:
            if len(f_i[1]) == 1:
                return f_i[1][0](self.x__iface, self.x__base + f_i[0])
            # pass addititional argument to the constructor
            return f_i[1][0](self.x__iface, self.x__base + f_i[0], f_i[1][1])

    def _verify_id(self):
        id = self.ID.read()
        if id != self.x__id:
            raise Exception(
                self.__class__.__name__ + " has ID " + hex(self.x__id) + ", read ID " + hex(id)
            )

    def _verify_ver(self):
        ver = self.VER.read()
        if ver != self.x__ver:
            raise Exception(
                self.__class__.__name__ + " has VER " + hex(self.x__ver) + ", read VER " + hex(ver)
            )

    def verify_id_and_version(self):
        """Read and verify id (ID) and version (VER) registers values.

        This function reads and verifies ID and VER register values
        in a recursive way for all non black box blocks.
        It raises the exception if read values differ as it indicates,
        that software and firmware versions differ.
        """
        for k in self.x__fields.keys():
            subblock = getattr(self, k)
            if not issubclass(type(subblock), Block):
                continue

        if self.x__is_blackbox == False:
            self._verify_id()
            self._verify_ver()

    def dispatch(self):
        self.x__iface.dispatch()

class _Register(object):
    """Base class supporting access to the register."""

    x__size = 1

    def __init__(self, iface, base, bfields={}):
        self.x__iface = iface
        self.x__base = base
        self.x__bfields = bfields

    def __dir__(self):
        return self.x__bfields.keys()

    def read(self):
        """ Simple read method. Does not use any access optimization.
            The read is performed immediately, the result is
            masked, shifted and returned as integer. 
        """
        return self.x__iface.read(self.x__base)

    def readx(self):
        return self.x__iface.readx(self.x__base)
        """ Optimized read method. Schedules reading of the register.
            The "future" object is returned.
            When the "val" field in the returned value is accessed,
            The read is performed immediately (if not dispatched yet),
            and the result is returned as an integer.
        """    

    def read_fifo(self, count):
        return self.x__iface.read_fifo(self.x__base, count)

    def write(self, value):
        """ Simple write method. Does not use any access optimization.
            The write is performed immediately.
            Please note, that access to each bitfield generates
            a strobe pulse for the whole register (if strobe is implemented).
        """
        self.x__iface.write(self.x__base, value)

    def writex(self, value):
        """ Optimized write method. The write is only scheduled.
            It will be executed after the next "dispatch" call,
            or if the maximum length of the scheduled operations' list is
            achieved.
        """
        self.x__iface.writex(self.x__base, value)

    def write_fifo(self, values):
        self.x__iface.write(self.x__base, values)

    def rmw(self, mask, value, now=True):
        """ Optimized read-modify-write method. Multiple rmw commands
            done on the same register are aggregated into a single rmw.
            Reading of the register is scheduled after the first rmw
            is executed.
            If "now" is True, or another operation than rmw to the same
            register is executed, the write is scheduled with current
            mask and value, resulting from rmws aggregated up to now.
        """        
        self.x__iface.rmw(self.x__base, mask, value)
        if now:
            self.x__iface.rmw()
        

    def dispatch(self):
        self.x__iface.dispatch()

    def __getattr__(self, name):
        return _BitFieldAccess(self.x__iface, self.x__base, self.x__bfields[name])


ControlRegister = _Register  # The control register is just the generic register


class StatusRegister(_Register):
    """Class supporting access to the read-only (status) register.

    The write method throws an exception.
    """

    def write(self, value):
        raise Exception("Status register at " + hex(self.x__base) + " can't be written")


"""
Below is the demo code, showing an example how we may access the registers
via an emulated interface.
Please remember that in the real solution the functionality will be split
into two parts: in the HW backend, and in the gateway application.
"""
if __name__ == "__main__":
    # Table emulating the register file
    rf = 1024 * [
        int(0),
    ]

    # The class iface provides just two methods
    # read(address) and write(address,value)
    class DemoIface(object):
        def __init__(self):
            self.opers = [] # List of operations
            self.rmw_df = None # Future object for current RMW
            self.rmw_addr = None # RMW address for aggregated RMW commands
            self.rmw_mask = 0 # Mask for the aggregated RMW commands
            self.rmw_nval = 0 # Value for the aggregated RMW commands
            pass
        
        class DI_future(object):
            def __init__(self,iface):
                self.iface = iface
                self.done = False
                self._val = None
            def __getattr__(self,name):
                if name == "val":
                    # Check if the transaction is executed
                    if self.done:
                        return self._val
                    else:
                        self.iface.dispatch()
                        if self.done:
                            return self._val
                        else:
                            raise Exception("val not set after dispatch!")
            def set(self, val):
                self.done = True
                self._val = val     

        def read(self, addr):
            self.rmw() # Finalize any pending RMW
            if self.opers:
                self.dispatch()
            return self._read(addr)
            
        def _read(self, addr):
            global rf
            print("reading from address:" + hex(addr) + " val=" + hex(rf[addr]))
            return rf[addr]

        def write(self, addr, val):
            self.rmw() # Finalize any pending RMW
            if self.opers:
                self.dispatch()
            self._write(addr,val)

        def _write(self, addr, val):            
            global rf
            print("writing " + hex(val) + " to address " + hex(addr))
            rf[addr] = val

        def writex(self, addr, val):
            self.rmw() # Finalize any pending RMW
            self.opers.append(lambda : self._write(addr, val))
        
        def readx(self, addr):
            self.rmw() # Finalize any pending RMW
            df = self.DI_future(self)
            self.opers.append(lambda : df.set(self._read(addr)))
            return df
        
        def _rmw(self, df, addr, mask, nval):
            # The real HW implemented RMW
            dval = df.val | mask
            dval ^= mask
            dval |= nval
            self._write(addr, dval)
            
        def rmw(self, addr=None, mask=0, val=0):
            # Call to RMW without arguments simply finalizes the last RMW
            # Check if another RMW is being prepared
            if (self.rmw_addr is not None) and (addr != self.rmw_addr):
                # Finalize the previous RMW
                # We must copy the values, as they may be overwritten at the time of execution!
                odf = self.rmw_df
                mask = self.rmw_mask
                waddr = self.rmw_addr
                nval = self.rmw_nval 
                self.opers.append(lambda : self._rmw(odf, waddr, mask, nval))
                self.rmw_addr = None
                self.rmw_df = None
            if addr is not None: 
                # Schedule reading of the initial value of the register
                if self.rmw_addr is None:
                    df = self.DI_future(self)
                    self.opers.append(lambda : df.set(self._read(addr)))
                    self.rmw_df = df
                    self.rmw_addr = addr
                # Now aggregate the current operation
                self.rmw_mask |= mask
                self.rmw_nval |= mask
                self.rmw_nval ^= mask
                self.rmw_nval |= (val & mask)               
        
        def dispatch(self):
            if not self.opers:
                print("empty dispatch")
                return
            print("before dispatch")
            for x in self.opers:
                x()
            self.opers = []
            print("after dispatch")
        

    class c2(Block):
        x__size = 3
        x__fields = {
            "r1": (
                1,
                (
                    StatusRegister,
                    {"t1": BitField(3, 1, False), "t2": BitField(9, 4, False),},
                ),
            )
        }

    class regs(Block):
        x__size = 4
        x__fields = {
           "rv" : (
             1,
             (
                ControlRegister, {},
             ),
           ) 
        }
        
    class c1(Block):
        x__size = 100
        x__fields = {"f1": (0, 10, (c2,)), "f2": (11, (c2,)), "size": (32, (c2,)),"x1":(40,5,(regs,))}

    mf = DemoIface()
    a = c1(mf, 12)
    
    # Check if two consecutive BF writes do not interfere 
    a.f1[0].r1.t2.writex(11,False)
    print("1")
    a.f1[0].r1.t1.writex(5,False) # We intentionally "forget" to finalize that RMW, to see 
                                  # if the autoamted handling works
    print("2")
    a.f2.r1.t1.writex(7,False)
    print("3")
    a.f2.r1.t2.writex(13,True)
    a.x1[3].rv.write(5)
    a.x1[1].rv.write(7)    
    p1 = a.f1[0].r1.t2.readx()
    p2 = a.f1[0].r1.t1.readx()
    a.dispatch()
    print(p1.val,p2.val)
    p3 = a.x1[1].rv.readx()
    p4 = a.x1[3].rv.readx()
    print(p3.val,p4.val)
    print(a.f2.r1.t2.read())
    print(a.f2.r1.t1.read())
