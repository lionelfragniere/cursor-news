FROM nginx:1.27-alpine
RUN sed -i 's/listen       80;/listen       8080;/' /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html/
