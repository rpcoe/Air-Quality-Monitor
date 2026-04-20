import ssl

# Just create the default context and don't feed it any 'roots.pem' file.
# By default, if it has no certificates to compare against, 
# it will often proceed without verification or allow you to 
# set the verification mode to 'False' if your version supports it.
context = ssl.create_default_context()

# If your firmware supports it, this is the most direct way:
try:
    context.verify_mode = 0 # 0 is equivalent to CERT_NONE in many MicroPython/CircuitPython ports
except AttributeError:
    pass # If it's not supported, it usually defaults to a simpler behavior