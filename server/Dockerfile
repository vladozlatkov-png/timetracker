FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.js migrate.js ./
EXPOSE 8787
USER node
CMD ["node", "server.js"]
