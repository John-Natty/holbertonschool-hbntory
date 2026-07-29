FROM nginx:alpine

# Sert les fichiers statiques du client public.
COPY index.html style.css script.js background.js /usr/share/nginx/html/

# Illustrations des cartes produits, une par catégorie.
COPY img/ /usr/share/nginx/html/img/

EXPOSE 80
