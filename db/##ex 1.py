##ex 2.5
from math import *
'''care = lambda x,y: x*(y[0]) + str("\n") + x*(y[0] + (x-2)*y[1] + y[0] + "\n") + x*(y[0])
x,y=int(input("donnez un entier")),input("donnez un caractere")
print(care(x,y))
##ex 2.6 (fonction eval si on veut donner la fonction)
#qst 1:
def derive(f,x):
    return (f(x+10**(-6))-f(x))/10**(-6)
def carre(x):
    return x**2
x= float(input("donnez un nombre"))
print(derive(carre,x)) 
##ex 2.7
#qst 1
def logfx(u,x):
    return log(u(x))
#qst 2
def carre(x):
    return x**2
print(logfx(carre,5))
#qst 3
def logf(u):
    return log(u)
#qst4
print(logf(carre(5)))
'''
##ex 